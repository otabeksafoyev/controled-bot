"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram userbot (MTProto) — https://my.telegram.org/apps
    TELEGRAM_API_ID: int
    TELEGRAM_API_HASH: str
    TELEGRAM_STRING_SESSION: str = ""

    # Control bot (Bot API) — @BotFather
    CONTROL_BOT_TOKEN: str
    OWNER_ID: int

    # Ingest kanal — userbot video'ni shu yerga forward qiladi.
    # Control bot ushbu kanalda admin bo'lishi shart.
    INGEST_CHANNEL_ID: int

    # Kaworai bilan umumiy DB
    DB_URL: str

    # Parser
    MIN_VIDEO_DURATION: int = 60
    ENABLE_NAME_FALLBACK: bool = True

    LOG_LEVEL: str = Field(default="INFO")


settings = Settings()  # type: ignore[call-arg]
