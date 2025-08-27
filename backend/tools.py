import os, re, json
from typing import Optional, List, Tuple, Dict, Any

# ---- Config / sandbox -------------------------------------------------------
FS_ROOT  = os.path.abspath(os.environ.get("ELYSIA_FS_ROOT", os.getcwd()))
WORKDIR  = os.path.abspath(os.environ.get("ELYSIA_WORKDIR", os.path.join(FS_ROOT, "workspace")))
os.makedirs(WORKDIR, exist_ok=True)
MACRO_PATH = os.path.join(WORKDIR, "macros.json")

def _dir_hint_map() -> dict:
    home = os.path.expanduser("~")
    guesses = {
        "home": home,
        "desktop": os.path.join(home, "Desktop"),
        "downloads": os.path.join(home, "Downloads"),
        "documents": os.path.join(home, "Documents"),
        "docs": os.path.join(home, "Documents"),
        "music": os.path.join(home, "Music"),
        "pictures": os.path.join(home, "Pictures"),
        "videos": os.path.join(home, "Videos"),
        "repo": FS_ROOT,
        "project": FS_ROOT,
        "backend": os.path.join(FS_ROOT, "backend"),
        "frontend": os.path.join(FS_ROOT, "frontend"),
        "workspace": WORKDIR,
        "work": WORKDIR,
    }
    return {k: os.path.abspath(v) for k, v in guesses.items() if v and os.path.isdir(v)}

def _normalize_spoken_path(s: str) -> str:
    s = " " + s.strip().lower() + " "
    s = s.replace(" dot ", ".").replace(" period ", ".").replace(" point ", ".")
    s = s.replace(" slash ", "/").replace(" backslash ", "/").replace(" forward slash ", "/")
    s = s.replace(" under score ", "_").replace(" underscore ", "_")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _pop_any(d: dict, *keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d.pop(k)
    return None

def _join_safe(base: str, *parts: str) -> str:
    path = os.path.abspath(os.path.join(base, *parts))
    if not path.startswith(FS_ROOT + os.sep) and path != FS_ROOT:
        raise ValueError(f"path escapes sandbox: {path}")
    return path

def _parse_dir_hint(filename: str) -> Tuple[str, Optional[str]]:
    m = re.search(r"\b(in|to|into|under|on)\s+([a-z0-9_\-\/]+)\b", filename, re.I)
    hint = None
    if m:
        filename = (filename[:m.start()] + filename[m.end():]).strip()
        hint_key = m.group(2).lower()
        hint_map = _dir_hint_map()
        hint = hint_map.get(hint_key)
        if not hint and "/" in hint_key:
            head, *tail = hint_key.split("/")
            root = hint_map.get(head)
            if root:
                hint = os.path.join(root, *tail)
                if not os.path.isdir(hint):
                    hint = None
    return filename, hint

def _find_candidates(name: str, limit: int = 5) -> List[str]:
    name = _normalize_spoken_path(name).lower()
    cands = []
    for root, _, files in os.walk(FS_ROOT, topdown=True):
        for f in files:
            if name in f.lower():
                cands.append(os.path.join(root, f))
                if len(cands) >= limit:
                    return cands
    return cands

def create_file(filename: str, content: str = "", overwrite: bool = False) -> str:
    try:
        filename = _normalize_spoken_path(filename)
        filename, hint = _parse_dir_hint(filename)
        base = hint if hint else WORKDIR
        path = _join_safe(base, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "w" if overwrite else "x"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)
        rel = os.path.relpath(path, FS_ROOT)
        return f"OK: created {rel}"
    except FileExistsError:
        return "ERROR: file exists (use overwrite=true to replace)"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

def read_file(filename: str, max_bytes: Optional[int] = 1024 * 10) -> str:
    try:
        filename = _normalize_spoken_path(filename)
        filename, hint = _parse_dir_hint(filename)
        if not filename:
            return "ERROR: no filename given"
        path = _join_safe(WORKDIR, filename)
        if not os.path.exists(path):
            cands = _find_candidates(filename, limit=1)
            if cands:
                path = cands[0]
            else:
                return f"ERROR: not found: {filename}"
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
        if max_bytes is not None and len(data.encode("utf-8")) > max_bytes:
            return data[:max_bytes] + "\n\n[TRUNCATED]"
        return data
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

def list_dir(path: str = "") -> str:
    try:
        if not path:
            base = WORKDIR
        else:
            path = _normalize_spoken_path(path)
            _, hint = _parse_dir_hint(path)
            base = hint if hint else _join_safe(WORKDIR, path)
        base = os.path.abspath(base)
        if not os.path.isdir(base):
            return f"ERROR: not a directory: {base}"
        entries = []
        for name in sorted(os.listdir(base)):
            full = os.path.join(base, name)
            rel = os.path.relpath(full, FS_ROOT)
            entries.append(rel + ("/" if os.path.isdir(full) else ""))
        return "\n".join(entries) if entries else "(empty)"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

def find_file(name: str, limit: int = 5) -> str:
    try:
        cands = _find_candidates(name, limit=limit)
        if not cands:
            return "(no matches)"
        return "\n".join(os.path.relpath(p, FS_ROOT) for p in cands)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

class MacroStore:
    def __init__(self, path: str = MACRO_PATH):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._macros: Dict[str, Any] = {}
        self._load()
        self.max_macros = 10

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    self._macros = json.load(f)
        except Exception:
            self._macros = {}

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._macros, f, indent=2)

    def add(self, name: str, steps: list) -> str:
        if len(self._macros) >= self.max_macros:
            return "ERROR: macro limit reached—remove some first"
        if not name or not isinstance(name, str):
            return "ERROR: invalid macro name"
        if not isinstance(steps, list) or not steps:
            return "ERROR: steps must be a non-empty list"
        self._macros[name] = steps
        self._save()
        return f"OK: macro '{name}' saved with {len(steps)} step(s)"

    def remove(self, name: str) -> str:
        if name in self._macros:
            del self._macros[name]
            self._save()
            return f"OK: removed macro '{name}'"
        return f"ERROR: macro not found: {name}"

    def list(self) -> list:
        return sorted(self._macros.keys())

    def get(self, name: str):
        return self._macros.get(name)
