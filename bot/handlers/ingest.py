"""Ingest handler — control bot private chatda OWNER dan video oladi.

Userbot moslik topilgan videoni control botga private chat orqali yuboradi
(userbot = sizning akauntingiz). Control bot private message'ni qabul qiladi,
caption'dan metadata'ni parse qilib bot-API file_id ni `series` ga yozadi.

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


# Faqat OWNER dan kelgan private xabarlar
_OWNER_PRIVATE = (
    (F.chat.type == "private") & (F.from_user.id == settings.OWNER_ID) & F.caption.startswith(_CAPTION_PREFIX)
)


@router.message(_OWNER_PRIVATE, F.video)
async def on_video(message: Message) -> None:
    await _handle(message)


@router.message(_OWNER_PRIVATE, F.document)
async def on_document(message: Message) -> None:
    if message.document and not (message.document.mime_type or "").startswith("video/"):
        return
    await _handle(message)


async def _handle(message: Message) -> None:
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
