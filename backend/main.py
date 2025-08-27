import asyncio
import websockets
import json
import re
import requests
from concurrent.futures import ThreadPoolExecutor
import os
import ast

from prompts import format_user_prompt, SYSTEM_PROMPT
from tts import generate_audio_chunks, preload_tts
from stt import listen
from tools import create_file, read_file, list_dir, find_file, MacroStore

MODEL_NAME = os.environ.get("ELYSIA_MODEL", "orieg/gemma3-tools:1b-it-qat")

SAFE_TOOLS = {
    "create_file": create_file,
    "edit_file": create_file,
    "read_file": read_file,
    "read": read_file,
    "cat": read_file,
    "list_dir": list_dir,
    "ls": list_dir,
    "find_file": find_file,
    "find": find_file,
}

TOOL_BLOCK_RE = re.compile(r"```tool_code\s*(.*?)```", re.S)

_macro_store = MacroStore()

def add_macro_tool(name: str, steps: list) -> str:
    return _macro_store.add(name, steps)

def remove_macro_tool(name: str) -> str:
    return _macro_store.remove(name)

def list_macros() -> str:
    names = _macro_store.list()
    return "\n".join(names) if names else "(no macros)"

def run_macro(name: str) -> str:
    steps = _macro_store.get(name)
    if not steps:
        return f"ERROR: macro not found: {name}"
    results = []
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or "tool" not in step:
            results.append(f"ERROR: step {i} invalid")
            continue
        tool_name = step["tool"]
        kwargs = step.get("kwargs", {}) or {}
        fn = SAFE_TOOLS.get(tool_name)
        if not fn:
            results.append(f"ERROR: unknown tool: {tool_name}")
            continue
        try:
            results.append(str(fn(**kwargs)))
        except Exception as e:
            results.append(f"ERROR: {type(e).__name__}: {e}")
    return "\n".join(results)

SAFE_TOOLS.update({
    "add_macro_tool": add_macro_tool,
    "remove_macro_tool": remove_macro_tool,
    "list_macros": list_macros,
    "run_macro": run_macro,
})

def _run_tool_block(block: str) -> list[str]:
    results = []
    for line in block.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            call = ast.parse(line, mode="eval").body
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                results.append(f"ERROR: unsupported line: {line}")
                continue
            fn = SAFE_TOOLS.get(call.func.id)
            if not fn:
                results.append(f"ERROR: unknown tool: {call.func.id}")
                continue
            kwargs = {}
            for kw in call.keywords:
                kwargs[kw.arg] = ast.literal_eval(kw.value)
            results.append(str(fn(**kwargs)))
        except Exception as e:
            results.append(f"ERROR: {type(e).__name__}: {e}")
    return results

connected_clients = set()
speech_queue = asyncio.Queue()
scratchpad = []

async def broadcast(message_type: str):
    data = json.dumps({"type": message_type})
    for client in list(connected_clients):
        try:
            await client.send(data)
        except:
            pass

def clean_for_tts(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]", "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"(\s*\n\s*){2,}", "\n\n", text)
    return text.strip()

async def speaker_task():
    executor = ThreadPoolExecutor(max_workers=2)
    loop = asyncio.get_event_loop()
    while True:
        text = await speech_queue.get()
        if text is None:
            break
        await broadcast("speaking")
        audio_gen = await loop.run_in_executor(executor, generate_audio_chunks, text)
        async for chunk in audio_gen:
            pass  # Stream to frontend if needed
        speech_queue.task_done()
    executor.shutdown()

async def fetch_external_memory(user_input: str) -> str:
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    if not config.get('phone_home', False):
        return ""
    try:
        url = f"{config['memory_url']}?query={requests.utils.quote(user_input)}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except Exception as e:
        print(f"Memory fetch failed: {e}")
        return ""

def get_scratchpad_context():
    return "\n".join(f"[{role}] {msg}" for role, msg in scratchpad)

async def handle_request(user_input: str):
    external_memory = await fetch_external_memory(user_input)
    memory_text = get_scratchpad_context() + ("\n" + external_memory if external_memory else "")
    prompt = format_user_prompt(user_input, memory_text)
    scratchpad.append(("user", user_input))
    with open(os.path.join(os.path.dirname(__file__), 'config.json'), 'r') as f:
        config = json.load(f)
    scratchpad[:] = scratchpad[-config.get('recent_memory_limit', 5):]

    accum, tail = "", ""
    spoken = []

    import ollama
    resp = ollama.generate(model=MODEL_NAME, prompt=prompt, stream=True)

    TOKEN_TIMEOUT_S = 30
    async def _aiter_with_timeout(gen, timeout_s: float):
        loop = asyncio.get_event_loop()
        it = iter(gen)
        while True:
            try:
                yield await asyncio.wait_for(loop.run_in_executor(None, next, it), timeout=timeout_s)
            except asyncio.TimeoutError:
                break
            except StopIteration:
                break

    buf = []
    async for chunk in _aiter_with_timeout(resp, TOKEN_TIMEOUT_S):
        t = str(chunk)
        if t:
            buf.append(t)

    raw = "".join(buf)
    if not raw:
        return

    accum += raw

    while True:
        m = TOOL_BLOCK_RE.search(accum)
        if not m:
            break
        block = m.group(1)
        accum = accum[:m.start()] + accum[m.end():]
        for result in _run_tool_block(block):
            msg = clean_for_tts(result)
            if msg:
                await speech_queue.put(msg)
                spoken.append(msg)

    clean = clean_for_tts(accum)
    text = (tail + clean)[len(tail):]
    parts = re.split(r'(?<=[.!?])\s+', text)
    for s in parts[:-1]:
        s = s.strip()
        if s:
            await speech_queue.put(s)
            spoken.append(s)
    tail = parts[-1]

    last = clean_for_tts(tail).strip()
    if last:
        await speech_queue.put(last)
        spoken.append(last)

    response = " ".join(spoken).strip()
    if response:
        scratchpad.append(("assistant", response))

async def handle_interaction():
    await broadcast("idle")
    loop = asyncio.get_event_loop()
    while True:
        await broadcast("listening")
        user_input = await loop.run_in_executor(None, listen)
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "bye"}:
            await speech_queue.put("Goodbye!")
            await speech_queue.join()
            break
        await broadcast("thinking")
        await handle_request(user_input)
        await speech_queue.join()

async def websocket_handler(websocket, path=None):
    connected_clients.add(websocket)
    print("Client connected.")
    try:
        async for message in websocket:
            data = json.loads(message)
            if data.get("action") == "start":
                await handle_interaction()
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        connected_clients.discard(websocket)
        print("Client disconnected.")

async def main():
    preload_tts()
    speaker = asyncio.create_task(speaker_task())
    server = await websockets.serve(websocket_handler, "localhost", 8000)
    print("Elysia is running. WebSocket server on ws://localhost:8000")
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        pass
    finally:
        await speech_queue.put(None)
        speaker.cancel()
        server.close()
        await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
