"""Telethon userbot client setup."""

from __future__ import annotations

import logging

from telethon import TelegramClient
from telethon.sessions import StringSession

from config import settings

log = logging.getLogger(__name__)


def build_client() -> TelegramClient:
    """Return a configured TelegramClient (not yet started)."""
    if settings.TELEGRAM_STRING_SESSION:
        log.info("Userbot: StringSession ishlatilmoqda")
        session: StringSession | str = StringSession(settings.TELEGRAM_STRING_SESSION)
    else:
        log.info("Userbot: fayl asosidagi sessiya (user.session) ishlatilmoqda")
        session = "user"
    return TelegramClient(session, settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
