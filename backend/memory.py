# memory.py  — only the init() body changed
import re
import sqlite3
import aiosqlite
import asyncio
import time
from typing import List, Tuple

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
USING fts5(content, content_rowid='id');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', old.id, old.content);
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""

class MemoryStore:
    def __init__(self, path: str = "elysia_memory.sqlite"):
        self.path = path
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def init(self):
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            async with aiosqlite.connect(self.path) as db:
                # single shot – correctly handles BEGIN...END; trigger blocks
                await db.executescript(_SCHEMA)
                await db.commit()
            self._initialized = True

    async def add(self, role: str, content: str) -> int:
        await self.init()
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO messages(ts, role, content) VALUES (?, ?, ?)",
                (time.time(), role, content))
            await db.commit()
            return cur.lastrowid

    async def recent(self, limit: int = 6) -> List[Tuple[str, str]]:
        await self.init()
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
                (limit,))
            rows = await cur.fetchall()
        rows.reverse()
        return [(role, content) for (role, content) in rows]

    async def search(self, query: str, limit: int = 6):
        """
        Punctuation-safe MATCH: tokenize to words, build an OR query.
        Avoids FTS5 syntax errors on apostrophes etc.
        """
        await self.init()

        # extract alphanumeric tokens; keep length >= 2
        tokens = re.findall(r"[0-9A-Za-z]+", query)
        tokens = [t for t in tokens if len(t) >= 2]

        if not tokens:
            return []

        # 'foo OR bar OR baz'
        fts_query = " OR ".join(tokens)

        try:
            async with aiosqlite.connect(self.path) as db:
                cur = await db.execute(
                    """SELECT m.role, m.content
                         FROM messages_fts f
                         JOIN messages m ON m.id = f.rowid
                        WHERE messages_fts MATCH ?
                     ORDER BY m.id DESC
                        LIMIT ?""",
                    (fts_query, limit),
                )
                rows = await cur.fetchall()
        except sqlite3.Error as e:
            # fail soft — never take down the websocket over recall
            print(f"[memory.search] FTS error: {e!r} for query={fts_query!r}")
            return []

        rows.reverse()
        return [(role, content) for (role, content) in rows]

# Singleton helpers unchanged
_store = MemoryStore()

async def store_memory(user_input: str, assistant_response: str):
    await _store.add("user", user_input)
    await _store.add("assistant", assistant_response)

async def retrieve_relevant_memory(query: str, max_results: int = 4) -> str:
    search_results = await _store.search(query, limit=max_results)
    recent_results = await _store.recent(limit=max_results)
    combined, seen = [], set()
    for role, content in (search_results + recent_results):
        if content and content not in seen:
            combined.append(f"[{role}] {content}")
            seen.add(content)
    return "\n".join(combined)
