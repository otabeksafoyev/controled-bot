"""Userbot event handlers.

Yangi xabar kelganda:
1. Agar xabar **shaxsiy chat**da (kontakt) bo'lsa — avtojavob qoidalari tekshiriladi.
2. Aks holda (kanal xabari) — `watcher_channel_rules` ichida mos qoida qidiriladi:
   - Caption qoida pattern-iga mos kelsa, o'sha anime_id ga qism sifatida yuboriladi.
   - Video bo'lmasa, mos qoida bo'lmasa yoki dublikat bo'lsa — o'tkazib yuboriladi.
3. Mos qoida topilsa: watcher videoni kaworai SECRET_CHANNEL ga
   "ID: <anime_id>\\nQism: <episode>" caption bilan post qiladi.
4. Kaworai_bot o'zining `add_episode_from_channel` handleri bilan DB-ga yozadi.
"""

from __future__ import annotations

import logging

from telethon import TelegramClient, events
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
    PeerUser,
    User,
)

from config import settings
from db.engine import AsyncSessionLocal
from db.queries import (
    get_rules_for_channel,
    is_forwarded,
    list_active_auto_replies,
    mark_forwarded,
)
from userbot.matcher import parse_meta
from userbot.rules import match_pattern

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


async def _handle_channel_message(event: events.NewMessage.Event) -> None:
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
        rules: list = []
        matched_channel_id = peer_id
        for cid in candidates:
            rules = await get_rules_for_channel(session, cid)
            if rules:
                matched_channel_id = cid
                break
        if not rules:
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

        # FAQAT caption ni tekshiramiz (user tanlovi).
        caption_text = message.message or ""
        selected = None
        for rule in rules:
            if match_pattern(caption_text, rule.pattern, rule.pattern_type):
                selected = rule
                break
        if selected is None:
            log.info(
                "Skip (hech qaysi qoidaga mos kelmadi) channel=%s uid=%s caption=%r",
                matched_channel_id,
                unique_id,
                caption_text[:80],
            )
            return

        anime_id = selected.anime_id
        # Qism raqami — captiondan (fallback filename bilan)
        meta = parse_meta(caption_text or filename or "")
        episode = meta.episode if meta.episode is not None else 1

    caption_out = f"ID: {anime_id}\nQism: {episode}"
    try:
        await event.client.send_file(
            settings.SECRET_CHANNEL_ID,
            file=message.media,
            caption=caption_out,
        )
    except Exception:
        log.exception(
            "SECRET_CHANNEL ga yuborishda xato (anime=%s ep=%s uid=%s)",
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
        "Kaworai SECRET_CHANNEL ga yuborildi: anime=%s ep=%s uid=%s (qoida #%s pattern=%r)",
        anime_id,
        episode,
        unique_id,
        selected.id,
        selected.pattern,
    )


async def _handle_private_message(event: events.NewMessage.Event) -> None:
    """Kontaktdan kelgan shaxsiy xabarga avtojavob."""
    sender = await event.get_sender()
    if not isinstance(sender, User):
        return
    if sender.bot or sender.is_self:
        return
    # Faqat kontakt — Telegram User.contact flag
    if not getattr(sender, "contact", False):
        return

    text = event.message.message or ""
    if not text:
        return

    async with AsyncSessionLocal() as session:
        replies = await list_active_auto_replies(session)

    for reply in replies:
        if match_pattern(text, reply.pattern, reply.pattern_type):
            try:
                await event.client.send_message(sender.id, reply.reply_text)
            except Exception:
                log.exception("Avtojavob yuborishda xato (sender=%s)", sender.id)
            return


async def _dispatch(event: events.NewMessage.Event) -> None:
    # Shaxsiy chat (PeerUser) — avtojavob
    if isinstance(event.message.peer_id, PeerUser):
        await _handle_private_message(event)
        return
    # Kanal/guruh — kanal qoidalari
    await _handle_channel_message(event)


def register(client: TelegramClient) -> None:
    """Telethon handlerlarni ro'yxatdan o'tkazish."""

    @client.on(events.NewMessage(incoming=True))
    async def _on_new_message(event: events.NewMessage.Event) -> None:
        try:
            await _dispatch(event)
        except Exception:
            log.exception("Userbot xabarni qayta ishlashda xato")
