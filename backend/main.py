import asyncio
import websockets
import json
import re
from concurrent.futures import ThreadPoolExecutor
import os
import ast
import llm
import llm_ollama  # ensure plugin registers

from prompts import format_user_prompt, SYSTEM_PROMPT
from memory import store_memory, retrieve_relevant_memory
from tts import generate_audio_chunks, preload_tts
from stt import listen
from tools import create_file, read_file, list_dir, find_file, MacroStore

# Use the PLAIN Ollama model name (no 'ollama:' prefix)
MODEL_NAME = os.environ.get("ELYSIA_MODEL", "orieg/gemma3-tools:1b-it-qat")

SAFE_TOOLS = {
    "create_file": create_file,
    "edit_file": create_file,   # alias
    "read_file": read_file,
    "read": read_file,          # alias
    "cat": read_file,           # alias
    "list_dir": list_dir,
    "ls": list_dir,             # alias
    "find_file": find_file,
    "find": find_file,          # alias
}

TOOL_BLOCK_RE = re.compile(r"```tool_code\s*(.*?)```", re.S)

# persistent macro store (lives in workspace/macros.json)
_macro_store = MacroStore()

def add_macro_tool(name: str, steps: list) -> str:
    """
    Register a new 'macro tool' made of existing safe tools.
    steps: [{"tool": "create_file", "kwargs": {...}}, ...]
    """
    # lightweight validation here; strict validation during run
    return _macro_store.add(name, steps)

def remove_macro_tool(name: str) -> str:
    return _macro_store.remove(name)

def list_macros() -> str:
    names = _macro_store.list()
    return "\n".join(names) if names else "(no macros)"

def run_macro(name: str) -> str:
    """
    Execute a stored macro by running each step in order using SAFE_TOOLS.
    Returns newline-joined results from each step.
    """
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
    """
    Execute lines like: create_file(filename="elysia.txt", content="Elysia")
    Only calls SAFE_TOOLS with keyword args that ast.literal_eval can parse.
    Returns list of result strings (one per line).
    """
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
                if kw.arg is None:
                    raise ValueError("**kwargs not allowed")
                kwargs[kw.arg] = ast.literal_eval(kw.value)
            out = fn(**kwargs)
            results.append(str(out))
        except Exception as e:
            results.append(f"ERROR: {type(e).__name__}: {e}")
    return results


connected_clients = set()
speech_queue = asyncio.Queue()

TOKEN_TIMEOUT_S = 50      # per-token wait max
RESP_TIMEOUT_S  = 45      # per-response wait max

async def _aiter_with_timeout(aiter, item_timeout: float):
    """Async iterate with a per-item timeout; stops cleanly on stall."""
    it = aiter.__aiter__()
    while True:
        try:
            nxt = await asyncio.wait_for(it.__anext__(), item_timeout)
        except StopAsyncIteration:
            break
        except asyncio.TimeoutError:
            print(f"[llm] timeout waiting >{item_timeout}s for next chunk; aborting stream.")
            break
        yield nxt

async def broadcast(state: str, data: dict = None, audio_chunk=None):
    """Broadcast state + optional data/audio to all WS clients."""
    message = {"state": state, "data": data or {}}
    if audio_chunk is not None:
        message["audio_chunk"] = audio_chunk.tolist()  # float32 -> JSON-safe
    msg_json = json.dumps(message)
    for client in list(connected_clients):
        try:
            await client.send(msg_json)
        except websockets.exceptions.ConnectionClosed:
            connected_clients.discard(client)

async def speaker_task():
    """Consume text, TTS it, stream audio to clients."""
    while True:
        text = await speech_queue.get()
        if text is None:
            break  # shutdown
        await broadcast("speaking", {"response": text})
        print(f"Elysia (speaking): {text}")
        try:
            loop = asyncio.get_event_loop()
            # run blocking TTS in a worker
            with ThreadPoolExecutor() as executor:
                audio_chunks = await loop.run_in_executor(
                    executor, lambda: list(generate_audio_chunks(text))
                )
            for chunk in audio_chunks:
                await broadcast("speaking", {"response": ""}, audio_chunk=chunk)
        except Exception as e:
            print(f"Error in TTS: {e}")
        speech_queue.task_done()

# SINGLE async model instance; plain name (plugin maps it)
amodel = llm.get_async_model(MODEL_NAME)

FENCED_BLOCK_RE = re.compile(r"(?s)(```.*?```|'''[\s\S]*?''')")
INLINE_CODE_RE  = re.compile(r"`([^`]+)`")

def clean_for_tts(text: str) -> str:
    text = FENCED_BLOCK_RE.sub("", text)
    text = INLINE_CODE_RE.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()

async def handle_request(user_input: str):
    # 1) memory must never kill the turn
    try:
        memory_text = await retrieve_relevant_memory(user_input)
    except Exception as e:
        print(f"[memory] fallback: {e}")
        memory_text = ""

    # 2) build prompt
    prompt_text = format_user_prompt(user_input, memory_text)
    print(f"Prompt to LLM:\n{prompt_text}\n")

    # 3) build chain (tools available; we still catch ```tool_code``` ourselves)
    chain = amodel.chain(
        prompt_text,
        system=SYSTEM_PROMPT,
        tools=[create_file, read_file, list_dir, find_file],
    )

    accum = ""   # accumulated raw text (we remove tool blocks as we handle them)
    tail  = ""   # partial sentence between iterations
    spoken = []

    # iterate over responses with a response-level timeout
    async for resp in _aiter_with_timeout(chain.responses(), RESP_TIMEOUT_S):
        # stream tokens from this response with a per-token timeout
        buf = []
        async for chunk in _aiter_with_timeout(resp, TOKEN_TIMEOUT_S):
            t = str(chunk)
            if t:
                buf.append(t)

        raw = "".join(buf)
        if not raw:
            continue

        accum += raw

        # ---- execute any ```tool_code ...``` blocks that arrived ----
        while True:
            m = TOOL_BLOCK_RE.search(accum)
            if not m:
                break
            block = m.group(1)
            # remove executed block
            accum = accum[:m.start()] + accum[m.end():]
            # run tool lines and speak results
            for result in _run_tool_block(block):
                msg = clean_for_tts(result)
                if msg:
                    await speech_queue.put(msg)
                    spoken.append(msg)

        # ---- speak newly completed sentences from remaining non-code text ----
        clean = clean_for_tts(accum)
        text  = (tail + clean)[len(tail):]
        parts = re.split(r'(?<=[.!?])\s+', text)
        for s in parts[:-1]:
            s = s.strip()
            if s:
                await speech_queue.put(s)
                spoken.append(s)
        tail = parts[-1]  # keep trailing partial sentence

    # flush any leftover plain text after stream ends or times out
    last = clean_for_tts(tail).strip()
    if last:
        await speech_queue.put(last)
        spoken.append(last)

    # 4) store what was actually spoken
    await store_memory(user_input, " ".join(spoken).strip())

async def handle_interaction():
    """Sequential voice -> think -> speak loop (no input while speaking)."""
    await broadcast("idle")
    loop = asyncio.get_event_loop()
    while True:
        await broadcast("listening")
        # use default thread pool; don’t spawn a new executor every time
        user_input = await loop.run_in_executor(None, listen)
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "bye"}:
            await speech_queue.put("Goodbye!")
            await speech_queue.join()
            break
        await broadcast("thinking")
        await handle_request(user_input)
        await speech_queue.join()  # finish speaking before listening again

async def websocket_handler(websocket, path=None):
    """Attach a client; start interaction when it sends {"action":"start"}."""
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
        await asyncio.Future()  # run forever
    except KeyboardInterrupt:
        pass
    finally:
        await speech_queue.put(None)
        speaker.cancel()
        server.close()
        await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
