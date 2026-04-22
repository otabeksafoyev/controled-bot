"""Shared utilities for bot handlers."""

from __future__ import annotations

import contextlib
import logging

from aiogram.types import CallbackQuery, InaccessibleMessage, Message
from telethon import TelegramClient
from telethon.errors import UsernameNotOccupiedError
from telethon.tl.types import Channel

from config import settings

log = logging.getLogger(__name__)


def is_owner_message(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == settings.OWNER_ID)


def is_owner_callback(cb: CallbackQuery) -> bool:
    return bool(cb.from_user and cb.from_user.id == settings.OWNER_ID)


def accessible(cb: CallbackQuery) -> Message | None:
    """Return cb.message if it is an editable Message, else None.

    Aiogram's CallbackQuery.message may be InaccessibleMessage (too old to edit).
    """
    msg = cb.message
    if msg is None or isinstance(msg, InaccessibleMessage):
        return None
    return msg


def channel_id_to_db(channel_id: int) -> int:
    if channel_id < 0:
        return channel_id
    return int(f"-100{channel_id}")


async def resolve_channel(userbot: TelegramClient, raw: str) -> Channel | None:
    raw = raw.strip()
    if "t.me/+" in raw or "t.me/joinchat/" in raw:
        return None
    try:
        entity = await userbot.get_entity(raw)
    except (UsernameNotOccupiedError, ValueError):
        return None
    if isinstance(entity, Channel):
        return entity
    return None


async def get_channel_title(userbot: TelegramClient, channel_id: int) -> str | None:
    title: str | None = None
    with contextlib.suppress(Exception):
        entity = await userbot.get_entity(channel_id)
        title = getattr(entity, "title", None)
    return title
