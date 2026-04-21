"""Userbot event handlers.

Yangi xabar kelganda:
1. Manbaning kanal IDsi watcher_channel_links da bog'langan bo'lsa,
2. Xabarda video/document bo'lsa (minimal davomiylikdan katta),
3. file_unique_id allaqachon yuborilgan bo'lmasa,
4. Caption/fayl nomidan qism raqamini olish. Topilmasa — 1.
5. Userbot videoni kaworai_bot SECRET_CHANNEL ga post qiladi,
   "ID: <anime_id>\\nQism: <episode>" formatli caption bilan.
6. Kaworai_bot o'zining mavjud `add_episode_from_channel` handleri bilan
   DB-ga yozadi va bildirishnoma yuboradi.

Muhim: watcher kaworai DB-ga tegmaydi. Hamma narsa kaworai_bot'ning
o'z ishlash mantig'i orqali bajariladi.
"""

from __future__ import annotations

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
    get_links_for_channel,
    is_forwarded,
    mark_forwarded,
)
from userbot.matcher import parse_meta

log = logging.getLogger(__name__)


def _extract_video_meta(message: object) -> tuple[str | None, int, str | None]:
    """Return (file_unique_id, duration, filename) yoki (None, 0, None)."""
    media = getattr(message, "media", None)
    if not isinstance(media, MessageMediaDocument) or media.document is None:
        return None, 0, None
    doc = media.document
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
    file = getattr(message, "file", None)
    unique_id: str | None = getattr(file, "unique_id", None) if file else None
    return unique_id, duration, filename


async def _handle_new_message(event: events.NewMessage.Event) -> None:
    message = event.message
    peer_id = getattr(event.chat, "id", None)
    if peer_id is None:
        return

    # Telethon Channel.id pozitiv, lekin DB da -100… ko'rinishida saqlanadi.
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

        if await is_forwarded(session, unique_id):
            log.info("Skip (allaqachon yuborilgan) uid=%s", unique_id)
            return

        # Bir kanal bir nechta animega bog'langan bo'lsa, hozirgi turg'un
        # versiya faqat bitta bog'lanishni qo'llab-quvvatlaydi. Birinchisini
        # tanlaymiz — boshqa strategiya kerak bo'lsa /unlink orqali tozalang.
        anime_id = links[0].anime_id

        text_source = message.message or filename or ""
        meta = parse_meta(text_source)
        episode = meta.episode if meta.episode is not None else 1

    # Kaworai SECRET_CHANNEL ga post — kaworai_bot handleri uni qabul qiladi
    caption = f"ID: {anime_id}\nQism: {episode}"
    try:
        await event.client.send_file(
            settings.SECRET_CHANNEL_ID,
            file=message.media,
            caption=caption,
        )
    except Exception:
        log.exception(
            "SECRET_CHANNEL ga yuborishda xato (anime=%s ep=%s uid=%s) — "
            "siz bu kanalda post qila olishingizga ishonch hosil qiling",
            anime_id,
            episode,
            unique_id,
        )
        return

    async with AsyncSessionLocal() as session:
        await mark_forwarded(
            session,
            file_unique_id=unique_id,
            anime_id=anime_id,
            episode=episode,
            source_channel_id=matched_channel_id,
        )
        await session.commit()

    log.info(
        "Kaworai SECRET_CHANNEL ga yuborildi: anime=%s ep=%s uid=%s",
        anime_id,
        episode,
        unique_id,
    )


def register(client: TelegramClient) -> None:
    """Telethon handlerlarni ro'yxatdan o'tkazish."""

    @client.on(events.NewMessage(incoming=True))
    async def _on_new_message(event: events.NewMessage.Event) -> None:
        try:
            await _handle_new_message(event)
        except Exception:
            log.exception("Userbot xabarni qayta ishlashda xato")
