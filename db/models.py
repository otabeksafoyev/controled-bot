"""Watcher mahalliy SQLite modellari.

Eslatma: bu yerdagi jadvallar **watcher ga tegishli**. Kaworai_bot DB-si bilan
aloqasi yo'q — u boshqa joyda ishlaydi va o'z sxemasini o'zi boshqaradi.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# pattern_type qiymatlari
PATTERN_SUBSTRING = "substring"
PATTERN_REGEX = "regex"


class ChannelRule(Base):
    """Kanal uchun qoida: caption shu pattern-ga mos kelsa → anime_id ga qism qo'shadi.

    Bitta kanalda ko'p qoida bo'lishi mumkin. Qoidalar ko'rib chiqilgan tartibda:
    pattern bo'sh ("") bo'lsa — istalgan captionga mos keladi ("match-all" qoida).
    """

    __tablename__ = "watcher_channel_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pattern_type: Mapped[str] = mapped_column(String(16), nullable=False, default=PATTERN_SUBSTRING)
    anime_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AutoReply(Base):
    """Shaxsiy xabarlar uchun avtojavob qoidasi.

    Faqat kontaktlardan kelgan xabarlarga javob beriladi. Matn pattern-ga mos
    kelsa (substring yoki regex) — tayyor javob yuboriladi.
    """

    __tablename__ = "watcher_auto_replies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pattern_type: Mapped[str] = mapped_column(String(16), nullable=False, default=PATTERN_SUBSTRING)
    reply_text: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ForwardedFile(Base):
    """Yuborilgan fayllar — dedup uchun. file_unique_id universal (MTProto)."""

    __tablename__ = "watcher_forwarded"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_unique_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    anime_id: Mapped[int] = mapped_column(Integer, nullable=False)
    episode: Mapped[int] = mapped_column(Integer, nullable=False)
    source_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forwarded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
