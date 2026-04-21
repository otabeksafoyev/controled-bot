"""Watcher mahalliy DB so'rovlari."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ChannelLink, ForwardedFile


async def add_link(
    session: AsyncSession, *, channel_id: int, anime_id: int, created_by: int
) -> ChannelLink | None:
    existing = await session.scalar(
        select(ChannelLink).where(ChannelLink.channel_id == channel_id, ChannelLink.anime_id == anime_id)
    )
    if existing is not None:
        return None
    row = ChannelLink(channel_id=channel_id, anime_id=anime_id, created_by=created_by)
    session.add(row)
    await session.flush()
    return row


async def remove_link(session: AsyncSession, *, channel_id: int, anime_id: int | None = None) -> int:
    stmt = delete(ChannelLink).where(ChannelLink.channel_id == channel_id)
    if anime_id is not None:
        stmt = stmt.where(ChannelLink.anime_id == anime_id)
    result = await session.execute(stmt)
    return result.rowcount or 0


async def get_links_for_channel(session: AsyncSession, channel_id: int) -> list[ChannelLink]:
    result = await session.scalars(select(ChannelLink).where(ChannelLink.channel_id == channel_id))
    return list(result.all())


async def list_all_links(session: AsyncSession) -> list[ChannelLink]:
    result = await session.scalars(select(ChannelLink).order_by(ChannelLink.channel_id, ChannelLink.anime_id))
    return list(result.all())


async def is_forwarded(session: AsyncSession, file_unique_id: str) -> bool:
    result = await session.scalar(
        select(ForwardedFile.id).where(ForwardedFile.file_unique_id == file_unique_id)
    )
    return result is not None


async def mark_forwarded(
    session: AsyncSession,
    *,
    file_unique_id: str,
    anime_id: int,
    episode: int,
    source_channel_id: int | None,
) -> None:
    existing = await session.scalar(
        select(ForwardedFile).where(ForwardedFile.file_unique_id == file_unique_id)
    )
    if existing is not None:
        return
    row = ForwardedFile(
        file_unique_id=file_unique_id,
        anime_id=anime_id,
        episode=episode,
        source_channel_id=source_channel_id,
    )
    session.add(row)
    await session.flush()


async def recent_forwarded(session: AsyncSession, limit: int = 10) -> list[ForwardedFile]:
    result = await session.scalars(select(ForwardedFile).order_by(ForwardedFile.id.desc()).limit(limit))
    return list(result.all())
