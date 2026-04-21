"""Database access helpers used by userbot and control bot."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Anime, ChannelLink, ProcessedFile, Series


async def get_anime(session: AsyncSession, anime_id: int) -> Anime | None:
    result = await session.execute(select(Anime).where(Anime.id == anime_id))
    return result.scalar_one_or_none()


async def find_anime_by_title(session: AsyncSession, title: str) -> Anime | None:
    """Nomi bo'yicha case-insensitive taqqoslash."""
    result = await session.execute(select(Anime).where(func.lower(Anime.title) == title.lower()))
    return result.scalar_one_or_none()


async def get_series_by_unique_id(session: AsyncSession, file_unique_id: str) -> Series | None:
    result = await session.execute(select(Series).where(Series.file_unique_id == file_unique_id))
    return result.scalar_one_or_none()


async def get_series(session: AsyncSession, anime_id: int, episode: int) -> Series | None:
    result = await session.execute(
        select(Series).where(Series.anime_id == anime_id, Series.episode == episode)
    )
    return result.scalar_one_or_none()


async def max_episode(session: AsyncSession, anime_id: int) -> int:
    result = await session.execute(select(func.max(Series.episode)).where(Series.anime_id == anime_id))
    value = result.scalar_one_or_none()
    return int(value or 0)


async def add_series(
    session: AsyncSession,
    *,
    anime_id: int,
    episode: int,
    file_id: str,
    file_unique_id: str | None,
) -> Series:
    row = Series(anime_id=anime_id, episode=episode, file_id=file_id, file_unique_id=file_unique_id)
    session.add(row)
    await session.flush()
    return row


async def mark_processed(
    session: AsyncSession,
    *,
    file_unique_id: str,
    anime_id: int | None,
    episode: int | None,
    series_id: int | None,
    source_channel_id: int | None,
) -> None:
    stmt = (
        pg_insert(ProcessedFile)
        .values(
            file_unique_id=file_unique_id,
            anime_id=anime_id,
            episode=episode,
            series_id=series_id,
            source_channel_id=source_channel_id,
        )
        .on_conflict_do_nothing(index_elements=[ProcessedFile.file_unique_id])
    )
    await session.execute(stmt)


async def is_processed(session: AsyncSession, file_unique_id: str) -> bool:
    result = await session.execute(
        select(ProcessedFile.id).where(ProcessedFile.file_unique_id == file_unique_id)
    )
    return result.scalar_one_or_none() is not None


# ── Channel links ──


async def add_channel_link(
    session: AsyncSession, *, channel_id: int, anime_id: int, channel_title: str | None, created_by: int
) -> ChannelLink:
    stmt = (
        pg_insert(ChannelLink)
        .values(
            channel_id=channel_id,
            anime_id=anime_id,
            channel_title=channel_title,
            created_by=created_by,
        )
        .on_conflict_do_nothing(index_elements=["channel_id", "anime_id"])
        .returning(ChannelLink)
    )
    result = await session.execute(stmt)
    link = result.scalar_one_or_none()
    if link is None:
        existing = await session.execute(
            select(ChannelLink).where(ChannelLink.channel_id == channel_id, ChannelLink.anime_id == anime_id)
        )
        link = existing.scalar_one()
    return link


async def remove_channel_link(session: AsyncSession, *, channel_id: int, anime_id: int | None = None) -> int:
    """Remove a specific link or all links for a channel. Returns deleted count."""
    from sqlalchemy import delete

    stmt = delete(ChannelLink).where(ChannelLink.channel_id == channel_id)
    if anime_id is not None:
        stmt = stmt.where(ChannelLink.anime_id == anime_id)
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


async def get_links_for_channel(session: AsyncSession, channel_id: int) -> list[ChannelLink]:
    result = await session.execute(select(ChannelLink).where(ChannelLink.channel_id == channel_id))
    return list(result.scalars().all())


async def list_all_links(session: AsyncSession) -> list[ChannelLink]:
    result = await session.execute(select(ChannelLink).order_by(ChannelLink.id))
    return list(result.scalars().all())
