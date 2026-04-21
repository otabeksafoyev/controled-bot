"""SQLAlchemy models.

Kaworai_bot bilan bir xil PostgreSQL ishlatiladi. Anime/Series jadvallari
kaworai_bot tomonidan boshqariladi; biz ulardan faqat o'qiymiz (va `series`
jadvaliga yangi qatorlar qo'shamiz).

Bundan tashqari quyidagi yangi jadvallar qo'shiladi:
- channel_links: kanal -> anime_id bog'lanishi
- processed_files: file_unique_id dedup uchun
- series ustuni: file_unique_id (nullable) — mavjud jadvalga migration orqali
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.engine import Base

# ── Kaworai tomonidan boshqariladigan jadvallardan faqat o'qish uchun stub ──
# (biz ularga migration qilmaymiz; to'liq modellar kaworai_bot ichida)


class Anime(Base):
    __tablename__ = "animes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anime_id: Mapped[int] = mapped_column(Integer, ForeignKey("animes.id", ondelete="CASCADE"))
    episode: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[str] = mapped_column(String(300), nullable=False)
    # Yangi ustun (migration orqali qo'shiladi). Eski qatorlarda NULL bo'lishi mumkin.
    file_unique_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


# ── Watcher o'ziga tegishli jadvallar ──


class ChannelLink(Base):
    """Kanalni aniq anime-ga bog'laydi.

    channel_id — MTProto peer id (bigint, kanallar uchun -100… bilan boshlanadi).
    """

    __tablename__ = "watcher_channel_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    anime_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("animes.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (UniqueConstraint("channel_id", "anime_id", name="uq_channel_anime_link"),)


class ProcessedFile(Base):
    """Dedup uchun — bir xil file_unique_id ikki marta qo'shilmasligi uchun."""

    __tablename__ = "watcher_processed_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_unique_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    anime_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
