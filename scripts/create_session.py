"""Telethon StringSession yaratish uchun bir martalik helper.

Ishga tushirish:
    python scripts/create_session.py

Sizdan telefon raqam va kod so'raladi. Oxirida StringSession chiqadi — uni
.env faylidagi TELEGRAM_STRING_SESSION ga yozing.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession


def main() -> None:
    load_dotenv()
    api_id_raw = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id_raw or not api_hash:
        print("TELEGRAM_API_ID / TELEGRAM_API_HASH .env da bo'lishi kerak.", file=sys.stderr)
        sys.exit(1)
    api_id = int(api_id_raw)

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        session_str = client.session.save()
        print("\n===== TELEGRAM_STRING_SESSION =====")
        print(session_str)
        print("===================================")
        print("Bu qatorni .env ga TELEGRAM_STRING_SESSION=... shaklida yozing.")


if __name__ == "__main__":
    main()
