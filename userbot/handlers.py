"""Userbot event handlers.

Yangi xabar kelganda:
1. Manbaning kanal IDsi watcher_channel_links da bog'langan bo'lsa,
2. Xabarda video/document bo'lsa (minimal davomiylikdan katta),
3. file_unique_id allaqachon ro'yxatga olingan yoki series da mavjud bo'lsa — skip,
4. Caption/fayl nomidan qism raqamini olish. Topilmasa — max(episode)+1.
5. Xabarni ingest kanalga JSON-caption bilan forward qilish.
   Control bot ingest kanalni kuzatib, forward kelganda bot-level file_id ni
   olib DB ga (series) yozadi.
"""

from __future__ import annotations

import json
import logging

from telethon import TelegramClient, events
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
)

from config import settings
from db.engine import AsyncSessionLocal
from db.queries import (
    find_anime_by_title,
    get_links_for_channel,
    get_series,
    get_series_by_unique_id,
    is_processed,
    mark_processed,
    max_episode,
)
from userbot.matcher import parse_meta

log = logging.getLogger(__name__)


def _extract_video_meta(message: object) -> tuple[str | None, int, str | None]:
    """Return (file_unique_id, duration, filename) yoki (None, 0, None)."""
    media = getattr(message, "media", None)
    if not isinstance(media, MessageMediaDocument) or media.document is None:
        return None, 0, None
    doc = media.document
    # Fayl turi
    is_video = False
    duration = 0
    filename: str | None = None
    for attr in getattr(doc, "attributes", []) or []:
        if isinstance(attr, DocumentAttributeVideo):
            is_video = True
            duration = int(getattr(attr, "duration", 0) or 0)
        elif isinstance(attr, DocumentAttributeFilename):
            filename = attr.file_name
    if not is_video and not (doc.mime_type or "").startswith("video/"):
        return None, 0, None
    # Telethon'da file_unique_id Message.file.unique_id orqali olinadi
    file = getattr(message, "file", None)
    unique_id: str | None = getattr(file, "unique_id", None) if file else None
    return unique_id, duration, filename


async def _choose_episode_number(session, anime_id: int, parsed_episode: int | None) -> int:
    if parsed_episode is not None:
        return parsed_episode
    # Fallback: oxirgi + 1
    last = await max_episode(session, anime_id)
    return last + 1


async def _resolve_anime_id(
    session, links: list, caption_title: str | None, enable_name_fallback: bool
) -> int | None:
    """Agar kanal bitta animega bog'langan bo'lsa shunisi. Aks holda nomi bo'yicha."""
    if len(links) == 1:
        return links[0].anime_id
    if not enable_name_fallback or not caption_title:
        return None
    anime = await find_anime_by_title(session, caption_title)
    if anime is None:
        return None
    # Mos keladiganlar ichida nomi mos keladigani borligini tekshirish
    for link in links:
        if link.anime_id == anime.id:
            return anime.id
    return None


async def _handle_new_message(event: events.NewMessage.Event) -> None:
    message = event.message
    # Faqat kanallardan
    peer_id = getattr(event.chat, "id", None)
    if peer_id is None:
        return
    # Telethon Channel.id pozitiv, lekin DB da -100… ko'rinishida saqlanadi.
    # Ikkala formatda tekshirib ko'ramiz.
    candidates = [peer_id]
    if peer_id > 0:
        candidates.append(int(f"-100{peer_id}"))
    if peer_id < 0:
        raw = str(peer_id).lstrip("-")
        if raw.startswith("100"):
            candidates.append(int(raw[3:]))

    async with AsyncSessionLocal() as session:
        links: list = []
        matched_channel_id = peer_id
        for cid in candidates:
            links = await get_links_for_channel(session, cid)
            if links:
                matched_channel_id = cid
                break
        if not links:
            return

        unique_id, duration, filename = _extract_video_meta(message)
        if unique_id is None:
            return
        if duration and duration < settings.MIN_VIDEO_DURATION:
            log.info("Skip (qisqa video duration=%ss) uid=%s", duration, unique_id)
            return

        # Dedup: allaqachon qayta ishlangan yoki series da mavjud
        if await is_processed(session, unique_id):
            log.info("Skip (allaqachon processed) uid=%s", unique_id)
            return
        existing = await get_series_by_unique_id(session, unique_id)
        if existing is not None:
            await mark_processed(
                session,
                file_unique_id=unique_id,
                anime_id=existing.anime_id,
                episode=existing.episode,
                series_id=existing.id,
                source_channel_id=matched_channel_id,
            )
            await session.commit()
            log.info("Skip (series da mavjud) uid=%s", unique_id)
            return

        text_source = message.message or filename or ""
        meta = parse_meta(text_source)
        anime_id = await _resolve_anime_id(session, links, meta.title, settings.ENABLE_NAME_FALLBACK)
        if anime_id is None:
            log.info(
                "Skip: kanal %s bir nechta animega bog'langan, mos anime aniqlanmadi (title=%r)",
                matched_channel_id,
                meta.title,
            )
            return

        episode = await _choose_episode_number(session, anime_id, meta.episode)

        # (anime_id, episode) bor bo'lsa — skip (lekin processed deb belgilaymiz)
        dup = await get_series(session, anime_id, episode)
        if dup is not None:
            await mark_processed(
                session,
                file_unique_id=unique_id,
                anime_id=anime_id,
                episode=episode,
                series_id=dup.id,
                source_channel_id=matched_channel_id,
            )
            await session.commit()
            log.info("Skip (anime=%s ep=%s mavjud) uid=%s", anime_id, episode, unique_id)
            return

    # Ingest kanalga forward — control bot qabul qiladi va DB ga yozadi
    payload = {
        "v": 1,
        "anime_id": anime_id,
        "episode": episode,
        "file_unique_id": unique_id,
        "source_channel_id": matched_channel_id,
    }
    caption = "KWR_INGEST " + json.dumps(payload, ensure_ascii=False)
    try:
        await event.client.send_file(
            settings.INGEST_CHANNEL_ID,
            file=message.media,
            caption=caption,
        )
        log.info("Forward qilindi: anime=%s ep=%s uid=%s", anime_id, episode, unique_id)
    except Exception:
        log.exception("Ingest kanalga forward qilishda xato")


def register(client: TelegramClient) -> None:
    """Telethon handlerlarni ro'yxatdan o'tkazish."""

    @client.on(events.NewMessage(incoming=True))
    async def _on_new_message(event: events.NewMessage.Event) -> None:
        try:
            await _handle_new_message(event)
        except Exception:
            log.exception("Userbot xabarni qayta ishlashda xato")
