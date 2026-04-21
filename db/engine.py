"""SQLAlchemy async engine — mahalliy SQLite (watcher uchun).

Watcher kaworai DB-siga tegmaydi. U faqat o'z state'ini saqlaydi:
- watcher_channel_links: kanal → anime_id mapping
- watcher_forwarded: yuborilgan fayllar (dedup uchun)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings

# aiosqlite URL — fayl nisbatan yo'l
_url = f"sqlite+aiosqlite:///{settings.SQLITE_PATH}"

engine = create_async_engine(_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
