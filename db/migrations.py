"""Bir martalik migratsiyalar — startup vaqtida ishlatiladi.

Eski `watcher_channel_links` (1 qoida = 1 kanal → 1 anime) jadvali bor bo'lsa,
uning ichidagi qatorlarni yangi `watcher_channel_rules` jadvaliga ko'chiramiz
(bo'sh pattern bilan — match-all). So'ng eski jadvalni o'chirib tashlaymiz.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from db.models import PATTERN_SUBSTRING

log = logging.getLogger(__name__)


async def migrate_legacy_channel_links(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        if "watcher_channel_links" not in tables:
            return

        rows = (
            await conn.execute(text("SELECT channel_id, anime_id, created_by FROM watcher_channel_links"))
        ).all()

        migrated = 0
        for channel_id, anime_id, created_by in rows:
            # Dublikat oldini olish — bir xil (channel_id, pattern='', anime_id)
            existing = await conn.execute(
                text(
                    "SELECT id FROM watcher_channel_rules "
                    "WHERE channel_id = :cid AND pattern = '' AND anime_id = :aid"
                ),
                {"cid": channel_id, "aid": anime_id},
            )
            if existing.first() is not None:
                continue
            await conn.execute(
                text(
                    "INSERT INTO watcher_channel_rules "
                    "(channel_id, pattern, pattern_type, anime_id, created_by) "
                    "VALUES (:cid, '', :ptype, :aid, :cby)"
                ),
                {
                    "cid": channel_id,
                    "ptype": PATTERN_SUBSTRING,
                    "aid": anime_id,
                    "cby": created_by,
                },
            )
            migrated += 1

        await conn.execute(text("DROP TABLE watcher_channel_links"))
        log.info(
            "Legacy migration: watcher_channel_links -> watcher_channel_rules (%d qator)",
            migrated,
        )
