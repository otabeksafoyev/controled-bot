"""Bir martalik migratsiyalar — startup vaqtida ishlatiladi."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)


async def migrate_rules_to_channels(engine: AsyncEngine) -> None:
    """Eski `watcher_channel_rules` / `watcher_channel_links` dan channel_id larni
    yangi `watcher_channels` ga ko'chirish. Qoidalar endi kerak emas — anime
    avto-matching kaworai DB dan bo'ladi.
    """
    async with engine.begin() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

        distinct_channels: dict[int, int] = {}  # channel_id -> added_by

        if "watcher_channel_rules" in tables:
            rows = (
                await conn.execute(text("SELECT DISTINCT channel_id, created_by FROM watcher_channel_rules"))
            ).all()
            for channel_id, created_by in rows:
                distinct_channels.setdefault(int(channel_id), int(created_by))

        if "watcher_channel_links" in tables:
            rows = (
                await conn.execute(text("SELECT DISTINCT channel_id, created_by FROM watcher_channel_links"))
            ).all()
            for channel_id, created_by in rows:
                distinct_channels.setdefault(int(channel_id), int(created_by))

        for channel_id, added_by in distinct_channels.items():
            existing = await conn.execute(
                text("SELECT id FROM watcher_channels WHERE channel_id = :cid"),
                {"cid": channel_id},
            )
            if existing.first() is not None:
                continue
            await conn.execute(
                text("INSERT INTO watcher_channels (channel_id, added_by, active) " "VALUES (:cid, :aby, 1)"),
                {"cid": channel_id, "aby": added_by},
            )

        for old in ("watcher_channel_rules", "watcher_channel_links"):
            if old in tables:
                await conn.execute(text(f"DROP TABLE {old}"))
                log.info("Dropped legacy table: %s", old)

        if distinct_channels:
            log.info("Legacy migration: %d kanal ko'chirildi", len(distinct_channels))
