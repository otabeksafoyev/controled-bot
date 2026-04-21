"""Admin komandalar — faqat OWNER_ID chaqira oladi.

Komandalar:
/start        — yordam
/status       — userbot + DB holati
/channels     — barcha bog'langan kanallar ro'yxati
/subscribe <kanal> — userbot kanalga obuna bo'ladi (@username yoki invite link)
/unsubscribe <kanal>
/link <kanal> <anime_id>   — kanalni animega bog'laydi
/unlink <kanal> [<anime_id>] — bog'lanishni o'chirish
/resolve <kanal>           — kanal IDsini olish
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel

from config import settings
from db.engine import AsyncSessionLocal
from db.queries import (
    add_channel_link,
    get_anime,
    list_all_links,
    remove_channel_link,
)

log = logging.getLogger(__name__)
router = Router(name="admin")


def owner_only(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == settings.OWNER_ID)


router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not owner_only(message):
        return
    await message.answer(
        "<b>Kaworai Watcher</b>\n\n"
        "Komandalar:\n"
        "/status — holat\n"
        "/channels — bog'langan kanallar\n"
        "/subscribe &lt;@username yoki invite link&gt;\n"
        "/unsubscribe &lt;@username yoki id&gt;\n"
        "/link &lt;kanal&gt; &lt;anime_id&gt;\n"
        "/unlink &lt;kanal&gt; [&lt;anime_id&gt;]\n"
        "/resolve &lt;kanal&gt; — ID olish"
    )


@router.message(Command("status"))
async def cmd_status(message: Message, userbot: TelegramClient) -> None:
    if not owner_only(message):
        return
    try:
        me = await userbot.get_me()
        user_line = f"Userbot: @{me.username or me.first_name} (id={me.id})"
    except Exception as exc:
        user_line = f"Userbot: XATO — {exc}"
    async with AsyncSessionLocal() as session:
        links = await list_all_links(session)
    await message.answer(f"{user_line}\nBog'lanishlar: {len(links)}")


async def _resolve_channel(userbot: TelegramClient, raw: str) -> Channel | None:
    raw = raw.strip()
    # Invite link
    if "t.me/+" in raw or "t.me/joinchat/" in raw:
        return None  # importga alohida qaralsin
    try:
        entity = await userbot.get_entity(raw)
    except (UsernameNotOccupiedError, ValueError):
        return None
    if isinstance(entity, Channel):
        return entity
    return None


def _channel_id_to_db(channel_id: int) -> int:
    """Kanallar uchun -100<id> formatiga keltirish."""
    if channel_id < 0:
        return channel_id
    return int(f"-100{channel_id}")


@router.message(Command("resolve"))
async def cmd_resolve(message: Message, userbot: TelegramClient, command: Any) -> None:
    if not owner_only(message):
        return
    if not command.args:
        await message.answer("Foydalanish: /resolve &lt;@username yoki link&gt;")
        return
    entity = await _resolve_channel(userbot, command.args.strip())
    if entity is None:
        await message.answer("Kanal topilmadi yoki bu username/invite link emas.")
        return
    await message.answer(
        f"<b>{entity.title}</b>\nid: <code>{_channel_id_to_db(entity.id)}</code>\n"
        f"username: @{entity.username or '—'}"
    )


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, userbot: TelegramClient, command: Any) -> None:
    if not owner_only(message):
        return
    if not command.args:
        await message.answer("Foydalanish: /subscribe &lt;@username yoki invite link&gt;")
        return
    arg = command.args.strip()
    try:
        if "t.me/+" in arg or "/joinchat/" in arg:
            # Invite hash ajratish
            hash_part = arg.rsplit("+", 1)[-1] if "t.me/+" in arg else arg.rsplit("/", 1)[-1]
            with contextlib.suppress(UserAlreadyParticipantError):
                await userbot(ImportChatInviteRequest(hash_part))
            await message.answer("Obuna bo'lindi (invite link).")
            return
        entity = await userbot.get_entity(arg)
        await userbot(JoinChannelRequest(entity))
        await message.answer(f"Obuna bo'lindi: <b>{getattr(entity, 'title', arg)}</b>")
    except (InviteHashExpiredError, InviteHashInvalidError):
        await message.answer("Invite link yaroqsiz yoki muddati tugagan.")
    except ChannelPrivateError:
        await message.answer("Kanal yopiq — invite link kerak.")
    except FloodWaitError as exc:
        await message.answer(f"Telegram rate limit: {exc.seconds}s kutish kerak.")
    except Exception as exc:
        log.exception("subscribe xato")
        await message.answer(f"Xato: {exc}")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, userbot: TelegramClient, command: Any) -> None:
    if not owner_only(message):
        return
    if not command.args:
        await message.answer("Foydalanish: /unsubscribe &lt;@username yoki id&gt;")
        return
    try:
        entity = await userbot.get_entity(command.args.strip())
        await userbot(LeaveChannelRequest(entity))
        await message.answer("Obunadan chiqdim.")
    except Exception as exc:
        log.exception("unsubscribe xato")
        await message.answer(f"Xato: {exc}")


def _parse_channel_arg(value: str) -> int | str:
    """Raqam bo'lsa int, aks holda @username kabi string qaytaradi."""
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        return value


@router.message(Command("link"))
async def cmd_link(message: Message, userbot: TelegramClient, command: Any) -> None:
    if not owner_only(message):
        return
    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.answer("Foydalanish: /link &lt;kanal&gt; &lt;anime_id&gt;")
        return
    channel_raw, anime_raw = parts
    try:
        anime_id = int(anime_raw)
    except ValueError:
        await message.answer("anime_id butun son bo'lishi kerak.")
        return

    channel_arg = _parse_channel_arg(channel_raw)
    title: str | None = None
    if isinstance(channel_arg, str):
        entity = await _resolve_channel(userbot, channel_arg)
        if entity is None:
            await message.answer("Kanal topilmadi. Avval /subscribe qilib ko'ring.")
            return
        channel_id = _channel_id_to_db(entity.id)
        title = entity.title
    else:
        channel_id = channel_arg
        with contextlib.suppress(Exception):
            entity = await userbot.get_entity(channel_id)
            title = getattr(entity, "title", None)

    async with AsyncSessionLocal() as session:
        anime = await get_anime(session, anime_id)
        if anime is None:
            await message.answer(f"Anime topilmadi (id={anime_id}).")
            return
        await add_channel_link(
            session,
            channel_id=channel_id,
            anime_id=anime_id,
            channel_title=title,
            created_by=message.from_user.id if message.from_user else 0,
        )
        await session.commit()
    await message.answer(
        f"Bog'landi: kanal <code>{channel_id}</code> → anime #{anime_id} " f"(<b>{anime.title}</b>)"
    )


@router.message(Command("unlink"))
async def cmd_unlink(message: Message, command: Any) -> None:
    if not owner_only(message):
        return
    parts = (command.args or "").split()
    if not parts:
        await message.answer("Foydalanish: /unlink &lt;kanal_id&gt; [&lt;anime_id&gt;]")
        return
    try:
        channel_id = int(parts[0])
    except ValueError:
        await message.answer("Kanal ID raqam bo'lishi kerak. /resolve orqali ID ni bilib oling.")
        return
    anime_id = int(parts[1]) if len(parts) > 1 else None
    async with AsyncSessionLocal() as session:
        removed = await remove_channel_link(session, channel_id=channel_id, anime_id=anime_id)
        await session.commit()
    await message.answer(f"O'chirildi: {removed} bog'lanish.")


@router.message(Command("channels"))
async def cmd_channels(message: Message) -> None:
    if not owner_only(message):
        return
    async with AsyncSessionLocal() as session:
        links = await list_all_links(session)
    if not links:
        await message.answer("Bog'lanishlar yo'q.")
        return
    lines = [
        f"• <code>{link.channel_id}</code> → #{link.anime_id} " f"({link.channel_title or '—'})"
        for link in links
    ]
    await message.answer("\n".join(lines))
