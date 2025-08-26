import asyncio
from memory import _store

async def clear_memory():
    await _store.init()
    import aiosqlite
    async with aiosqlite.connect(_store.path) as db:
        await db.execute("DELETE FROM messages")
        await db.execute("DELETE FROM messages_fts")
        await db.commit()
    print("Memory wiped.")

if __name__ == "__main__":
    asyncio.run(clear_memory())
