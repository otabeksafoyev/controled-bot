"""Watcher mahalliy SQLite modellari.

Eslatma: bu yerdagi jadvallar **watcher ga tegishli**. Kaworai_bot DB-si bilan
aloqasi yo'q — u boshqa joyda ishlaydi va o'z sxemasini o'zi boshqaradi.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class ChannelLink(Base):
    """Kanal → anime_id bog'lanishi (foydalanuvchi /link orqali qo'shadi)."""

    __tablename__ = "watcher_channel_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    anime_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("channel_id", "anime_id", name="uq_channel_anime_link"),)


class ForwardedFile(Base):
    """Yuborilgan fayllar — dedup uchun. file_unique_id universal (MTProto)."""

    __tablename__ = "watcher_forwarded"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_unique_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    anime_id: Mapped[int] = mapped_column(Integer, nullable=False)
    episode: Mapped[int] = mapped_column(Integer, nullable=False)
    source_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forwarded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
