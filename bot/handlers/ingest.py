"""Ingest kanal handleri.

Userbot video'ni ingest kanalga JSON caption bilan forward qiladi. Control bot
shu kanal uchun admin bo'lgani uchun uning `channel_post`ini oladi, caption'dan
metadata'ni parse qilib bot-API file_id ni `series` ga yozadi.

Caption format: `KWR_INGEST {"v":1,"anime_id":...,"episode":...,
"file_unique_id":"...","source_channel_id":...}`
"""

from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.types import Message

from config import settings
from db.engine import AsyncSessionLocal
from db.queries import add_series, get_series, mark_processed

log = logging.getLogger(__name__)
router = Router(name="ingest")

_CAPTION_PREFIX = "KWR_INGEST "


def _payload_from_caption(caption: str | None) -> dict | None:
    if not caption or not caption.startswith(_CAPTION_PREFIX):
        return None
    raw = caption[len(_CAPTION_PREFIX) :].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


@router.channel_post(F.chat.id == settings.INGEST_CHANNEL_ID, F.video)
async def on_video_post(message: Message) -> None:
    await _handle_video(message)


@router.channel_post(F.chat.id == settings.INGEST_CHANNEL_ID, F.document)
async def on_doc_post(message: Message) -> None:
    # Ba'zi video fayllar document sifatida yuborilishi mumkin
    if message.document and not (message.document.mime_type or "").startswith("video/"):
        return
    await _handle_video(message)


async def _handle_video(message: Message) -> None:
    payload = _payload_from_caption(message.caption)
    if payload is None:
        return
    try:
        anime_id = int(payload["anime_id"])
        episode = int(payload["episode"])
        file_unique_id = str(payload["file_unique_id"])
    except (KeyError, TypeError, ValueError):
        log.warning("Ingest: noto'g'ri payload: %s", payload)
        return
    source_channel_id = payload.get("source_channel_id")

    media = message.video or message.document
    if media is None:
        return
    bot_file_id = media.file_id

    async with AsyncSessionLocal() as session:
        # Agar (anime_id, episode) allaqachon bor bo'lsa — dubl qo'shmaymiz.
        existing = await get_series(session, anime_id, episode)
        if existing is not None:
            await mark_processed(
                session,
                file_unique_id=file_unique_id,
                anime_id=anime_id,
                episode=episode,
                series_id=existing.id,
                source_channel_id=source_channel_id,
            )
            await session.commit()
            log.info("Ingest: mavjud (anime=%s ep=%s) — skip", anime_id, episode)
            return

        row = await add_series(
            session,
            anime_id=anime_id,
            episode=episode,
            file_id=bot_file_id,
            file_unique_id=file_unique_id,
        )
        await mark_processed(
            session,
            file_unique_id=file_unique_id,
            anime_id=anime_id,
            episode=episode,
            series_id=row.id,
            source_channel_id=source_channel_id,
        )
        await session.commit()
        log.info("Ingest: series qo'shildi id=%s anime=%s ep=%s", row.id, anime_id, episode)
