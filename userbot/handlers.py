"""Userbot event handlers.

Yangi xabar kelganda:
1. Agar xabar **shaxsiy chat**da (kontakt) bo'lsa — avtojavob qoidalari tekshiriladi.
2. Aks holda (kanal xabari) — video bo'lsa:
   - Kanal kuzatiladigan kanallar ro'yxatida bo'lishi shart.
   - Caption-dan qism raqami va kaworai DB-dagi anime nomi (case-insensitive
     substring) bo'yicha anime_id topiladi.
   - Mos kelsa → SECRET_CHANNEL ga "ID: X\\nQism: Y" caption bilan yuboradi.
   - Mos kelmasa yoki qism raqami yo'q bo'lsa → `watcher_pending` ga qo'shiladi
     va owner-ga inline tugmali xabar jo'natiladi.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from telethon import TelegramClient, events
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
    PeerChannel,
    PeerChat,
    PeerUser,
    User,
)

from bot.keyboards import pending_actions
from config import settings
from db.engine import AsyncSessionLocal
from db.queries import (
    add_pending,
    is_channel_tracked,
    is_forwarded,
    list_active_auto_replies,
    mark_forwarded,
)
from kaworai.queries import episode_exists, get_animes
from userbot.matcher import find_anime_match, parse_meta
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


def _channel_id_candidates(peer_id: int) -> list[int]:
    """Telethon Channel.id pozitiv, lekin biz DB da -100... ko'rinishida saqlaymiz."""
    candidates = [peer_id]
    if peer_id > 0:
        candidates.append(int(f"-100{peer_id}"))
    elif peer_id < 0:
        raw = str(peer_id).lstrip("-")
        if raw.startswith("100"):
            candidates.append(int(raw[3:]))
    return candidates


async def _notify_owner_pending(
    bot: Bot,
    *,
    pending_id: int,
    channel_title: str | None,
    caption: str,
    detected_title: str | None,
    detected_episode: int | None,
    reason: str,
) -> None:
    short_caption = (caption or "").strip().splitlines()[0] if caption else "(bo'sh)"
    if len(short_caption) > 200:
        short_caption = short_caption[:200] + "…"
    reason_lbl = {
        "no_match": "Anime topilmadi",
        "no_episode": "Qism raqami topilmadi",
        "season_only": "Faqat fasl (qism yo'q)",
    }.get(reason, reason)
    lines = [
        "<b>🎬 Yangi video — qo'lda hal qilish kerak</b>",
        f"Kanal: <b>{channel_title or '?'}</b>",
        f"Sabab: <i>{reason_lbl}</i>",
    ]
    if detected_title:
        lines.append(f"Taxminan: <code>{detected_title}</code>")
    if detected_episode is not None:
        lines.append(f"Qism: <b>{detected_episode}</b>")
    lines.append("")
    lines.append(f"Caption: {short_caption}")
    try:
        await bot.send_message(
            settings.OWNER_ID,
            "\n".join(lines),
            reply_markup=pending_actions(pending_id),
        )
    except Exception:
        log.exception("Owner-ga xabar yuborishda xato pending=%s", pending_id)


async def _handle_channel_message(event: events.NewMessage.Event, bot: Bot) -> None:
    message = event.message
    peer_id = getattr(event.chat, "id", None)
    if peer_id is None:
        return

    candidates = _channel_id_candidates(peer_id)

    async with AsyncSessionLocal() as session:
        tracked = False
        matched_channel_id = peer_id
        for cid in candidates:
            if await is_channel_tracked(session, cid):
                tracked = True
                matched_channel_id = cid
                break
        if not tracked:
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

    caption_text = message.message or ""
    parse = parse_meta(caption_text or filename or "")

    channel_title = getattr(event.chat, "title", None)

    # 1. Qism raqami shart
    if parse.episode is None:
        reason = "season_only" if parse.is_season_only else "no_episode"
        async with AsyncSessionLocal() as session:
            row = await add_pending(
                session,
                file_unique_id=unique_id,
                source_channel_id=matched_channel_id,
                source_message_id=int(getattr(message, "id", 0) or 0),
                caption=caption_text,
                detected_title=None,
                detected_episode=None,
                reason=reason,
            )
            await session.commit()
        if row is not None:
            await _notify_owner_pending(
                bot,
                pending_id=row.id,
                channel_title=channel_title,
                caption=caption_text,
                detected_title=None,
                detected_episode=None,
                reason=reason,
            )
        return

    # 2. Anime nomini DB dan topishga urinish
    animes = await get_animes()
    match = find_anime_match(caption_text, [(a.id, a.title) for a in animes])

    if match is None:
        async with AsyncSessionLocal() as session:
            row = await add_pending(
                session,
                file_unique_id=unique_id,
                source_channel_id=matched_channel_id,
                source_message_id=int(getattr(message, "id", 0) or 0),
                caption=caption_text,
                detected_title=None,
                detected_episode=parse.episode,
                reason="no_match",
            )
            await session.commit()
        if row is not None:
            await _notify_owner_pending(
                bot,
                pending_id=row.id,
                channel_title=channel_title,
                caption=caption_text,
                detected_title=None,
                detected_episode=parse.episode,
                reason="no_match",
            )
        return

    anime_id, matched_title = match
    episode = parse.episode

    # 3. Kaworai DB da shu qism allaqachon bor bo'lsa — skip
    if await episode_exists(anime_id, episode):
        log.info(
            "Skip (qism allaqachon bor) anime=%s[%s] ep=%s uid=%s",
            anime_id,
            matched_title,
            episode,
            unique_id,
        )
        async with AsyncSessionLocal() as session:
            await mark_forwarded(
                session,
                file_unique_id=unique_id,
                anime_id=anime_id,
                episode=episode,
                source_channel_id=matched_channel_id,
            )
            await session.commit()
        return

    # 4. SECRET_CHANNEL ga yuborish
    caption_out = f"ID: {anime_id}\nQism: {episode}"
    try:
        await event.client.send_file(
            settings.SECRET_CHANNEL_ID,
            file=message.media,
            caption=caption_out,
        )
    except Exception:
        log.exception(
            "SECRET_CHANNEL ga yuborishda xato anime=%s ep=%s uid=%s",
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
        "Forwarded: anime=%s[%s] ep=%s channel=%s uid=%s",
        anime_id,
        matched_title,
        episode,
        matched_channel_id,
        unique_id,
    )


async def _handle_private_message(event: events.NewMessage.Event) -> None:
    """Kontaktdan kelgan shaxsiy xabarga avtojavob."""
    sender = await event.get_sender()
    if not isinstance(sender, User):
        return
    if sender.bot or sender.is_self:
        return
    if not getattr(sender, "contact", False):
        return

    text_in = event.message.message or ""
    if not text_in.strip():
        return

    async with AsyncSessionLocal() as session:
        replies = await list_active_auto_replies(session)

    for r in replies:
        if match_pattern(text_in, r.pattern, r.pattern_type):
            try:
                await event.reply(r.reply_text)
            except Exception:
                log.exception("Avtojavob yuborishda xato reply_id=%s", r.id)
            return


async def _dispatch(event: events.NewMessage.Event, bot: Bot) -> None:
    peer = event.message.peer_id if event.message else None
    if isinstance(peer, PeerUser):
        await _handle_private_message(event)
        return
    if isinstance(peer, PeerChannel | PeerChat):
        await _handle_channel_message(event, bot)


def register(client: TelegramClient, bot: Bot) -> None:
    @client.on(events.NewMessage(incoming=True))
    async def _on_new(event: events.NewMessage.Event) -> None:
        try:
            await _dispatch(event, bot)
        except Exception:
            log.exception("Userbot handleri xato")
