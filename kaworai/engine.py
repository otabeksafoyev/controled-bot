"""Async engine kaworai PostgreSQL DB-si uchun (read-only)."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from config import settings

log = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_SessionLocal: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine | None:
    global _engine, _SessionLocal
    if not settings.KAWORAI_DATABASE_URL:
        return None
    if _engine is None:
        url = settings.KAWORAI_DATABASE_URL
        # postgres:// -> postgresql+asyncpg:// (oddiy xato uchun)
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        _engine = create_async_engine(url, echo=False, future=True, pool_pre_ping=True)
        _SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
        log.info("Kaworai DB engine ulandi: %s", url.split("@")[-1])
    return _engine


def get_session() -> AsyncSession | None:
    get_engine()
    if _SessionLocal is None:
        return None
    return _SessionLocal()
