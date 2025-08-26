# tools.py — path-tolerant file helpers for voice use
import os, re, json
from typing import Optional, List, Tuple, Dict, Any

# ---- Config / sandbox -------------------------------------------------------
# All file operations are confined under this root.
FS_ROOT  = os.path.abspath(os.environ.get("ELYSIA_FS_ROOT", os.getcwd()))
WORKDIR  = os.path.abspath(os.environ.get("ELYSIA_WORKDIR", os.path.join(FS_ROOT, "workspace")))
os.makedirs(WORKDIR, exist_ok=True)
MACRO_PATH = os.path.join(WORKDIR, "macros.json")

# Common dir hints for voice: "desktop", "downloads", "repo", "backend", etc.
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

# ---- Normalization / safety -------------------------------------------------
def _normalize_spoken_path(s: str) -> str:
    # handle STT artifacts: "dot", "slash", etc.
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
    """
    Accept 'notes in desktop', 'report to workspace', 'foo/bar',
    returns (basename_or_relpath, hint_dir_abspath|None)
    """
    m = re.search(r"\b(in|to|into|under|on)\s+([a-z0-9_\-\/]+)\b", filename, re.I)
    hint = None
    if m:
        filename = (filename[:m.start()] + filename[m.end():]).strip()
        hint_key = m.group(2).lower()
        hint_map = _dir_hint_map()
        hint = hint_map.get(hint_key)
        # allow subpath hints like "repo/backend"
        if not hint and "/" in hint_key:
            head, *tail = hint_key.split("/")
            root = hint_map.get(head)
            if root:
                hint = os.path.join(root, *tail)
                if not os.path.isdir(hint):
                    os.makedirs(hint, exist_ok=True)
    return filename.strip(), os.path.abspath(hint) if hint else None

def _ensure_txt(name: str) -> str:
    # If no extension, default to .txt for voice UX
    return name if "." in os.path.basename(name) else f"{name}.txt"

def _resolve_target(filename: str, create_dirs: bool = True) -> str:
    # normalize voice-y strings and optional dir hint phrase
    filename = _normalize_spoken_path(filename)
    filename, hint_dir = _parse_dir_hint(filename)
    filename = filename.strip().strip('"').strip("'")
    filename = filename.replace(" ", "_")  # safer default for voice input

    # allow relative subpaths like "notes/idea"
    rel = filename
    if not any(sep in filename for sep in ("/", os.sep)):
        rel = _ensure_txt(filename)

    base = hint_dir if hint_dir else WORKDIR
    if create_dirs:
        os.makedirs(base, exist_ok=True)
        # also create any subfolders in rel
        subdir = os.path.dirname(rel)
        if subdir:
            os.makedirs(_join_safe(base, subdir), exist_ok=True)

    return _join_safe(base, rel)

def _find_candidates(query: str, limit: int = 10) -> List[str]:
    """Fuzzy search within FS_ROOT for files that match query (case-insensitive)."""
    q = _normalize_spoken_path(query)
    q = q.strip().strip('"').strip("'")
    hits: List[str] = []
    for root, _, files in os.walk(FS_ROOT):
        for f in files:
            p = os.path.join(root, f)
            if len(hits) >= limit:
                break
            if q in f.lower():
                hits.append(p)
    return hits

# ---- Tools ------------------------------------------------------------------
def create_file(filename: Optional[str] = None, content: Optional[str] = None, **kwargs) -> str:
    """
    Create or overwrite a text file. Voice-friendly path handling.
    Accepts aliases: filename|path|name|file , content|text|body|data|contents
    """
    # accept common aliases from tool_code
    if filename in (None, ""):
        filename = _pop_any(kwargs, "path", "name", "file", "filepath", "file_path", "target")
    if content is None:
        content = _pop_any(kwargs, "text", "body", "data", "contents", "value")
    if filename in (None, ""):
        return "ERROR: missing filename"
    if content is None:
        content = ""

    try:
        path = _resolve_target(filename, create_dirs=True)
        if os.path.exists(path):
            os.replace(path, f"{path}.bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"OK: wrote {len(content)} bytes to {os.path.relpath(path, FS_ROOT)}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

def read_file(filename: Optional[str] = None, max_bytes: Optional[int] = 200_000, **kwargs) -> str:
    """
    Read a file by name, relative path, or fuzzy name (no exact path needed).
    Accepts aliases: filename|path|name|file
    """
    if filename in (None, ""):
        filename = _pop_any(kwargs, "path", "name", "file", "filepath", "file_path", "target")
    if filename in (None, ""):
        return "ERROR: missing filename"

    try:
        try:
            path = _resolve_target(filename, create_dirs=False)
        except Exception:
            path = None

        if not path or not os.path.exists(path):
            if "/" not in filename and "\\" not in filename:
                cands = _find_candidates(filename, limit=3)
                if not cands:
                    return f"ERROR: file not found: {filename}"
                path = cands[0]
            else:
                return f"ERROR: file not found: {filename}"

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
        if max_bytes is not None and len(data.encode("utf-8")) > max_bytes:
            return data[:max_bytes] + "\n\n[TRUNCATED]"
        return data
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

def list_dir(path: str = "") -> str:
    """
    List files in a directory. Accepts hints like 'workspace', 'repo/backend',
    or empty to list WORKDIR.
    """
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

def find_file(name: str, limit: int = 10) -> str:
    """
    Fuzzy find files anywhere under the sandbox root.
    """
    try:
        cands = _find_candidates(name, limit=limit)
        if not cands:
            return "(no matches)"
        return "\n".join(os.path.relpath(p, FS_ROOT) for p in cands)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"

# --- MACRO TIME --------------------------------------------------------------
class MacroStore:
    def __init__(self, path: str = MACRO_PATH):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._macros: Dict[str, Any] = {}
        self._load()

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
        if not name or not isinstance(name, str):
            return "ERROR: invalid macro name"
        if not isinstance(steps, list) or not steps:
            return "ERROR: steps must be a non-empty list"
        # steps are validated at execution time in main (against SAFE_TOOLS)
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
