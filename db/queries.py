"""Watcher mahalliy DB so'rovlari."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AutoReply, Channel, ForwardedFile, PendingVideo

# ---------- Channel ----------


async def add_channel(
    session: AsyncSession,
    *,
    channel_id: int,
    title: str | None,
    username: str | None,
    added_by: int,
) -> Channel:
    existing = await session.scalar(select(Channel).where(Channel.channel_id == channel_id))
    if existing is not None:
        existing.title = title or existing.title
        existing.username = username or existing.username
        existing.active = True
        await session.flush()
        return existing
    row = Channel(
        channel_id=channel_id,
        title=title,
        username=username,
        added_by=added_by,
        active=True,
    )
    session.add(row)
    await session.flush()
    return row


async def remove_channel(session: AsyncSession, *, channel_id: int) -> int:
    result = await session.execute(delete(Channel).where(Channel.channel_id == channel_id))
    return result.rowcount or 0


async def get_channel(session: AsyncSession, channel_id: int) -> Channel | None:
    return await session.scalar(select(Channel).where(Channel.channel_id == channel_id))


async def list_channels(session: AsyncSession) -> list[Channel]:
    result = await session.scalars(select(Channel).order_by(Channel.title, Channel.channel_id))
    return list(result.all())


async def is_channel_tracked(session: AsyncSession, channel_id: int) -> bool:
    row = await session.scalar(
        select(Channel.id).where(Channel.channel_id == channel_id, Channel.active.is_(True))
    )
    return row is not None


# ---------- AutoReply ----------


async def add_auto_reply(
    session: AsyncSession,
    *,
    pattern: str,
    pattern_type: str,
    reply_text: str,
    created_by: int,
) -> AutoReply:
    row = AutoReply(
        pattern=pattern,
        pattern_type=pattern_type,
        reply_text=reply_text,
        created_by=created_by,
        active=True,
    )
    session.add(row)
    await session.flush()
    return row


async def remove_auto_reply(session: AsyncSession, *, reply_id: int) -> int:
    result = await session.execute(delete(AutoReply).where(AutoReply.id == reply_id))
    return result.rowcount or 0


async def toggle_auto_reply(session: AsyncSession, *, reply_id: int) -> AutoReply | None:
    row = await session.get(AutoReply, reply_id)
    if row is None:
        return None
    row.active = not row.active
    await session.flush()
    return row


async def list_auto_replies(session: AsyncSession) -> list[AutoReply]:
    result = await session.scalars(select(AutoReply).order_by(AutoReply.id))
    return list(result.all())


async def list_active_auto_replies(session: AsyncSession) -> list[AutoReply]:
    result = await session.scalars(select(AutoReply).where(AutoReply.active.is_(True)).order_by(AutoReply.id))
    return list(result.all())


async def get_auto_reply(session: AsyncSession, reply_id: int) -> AutoReply | None:
    return await session.get(AutoReply, reply_id)


# ---------- ForwardedFile ----------


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


# ---------- PendingVideo ----------


async def add_pending(
    session: AsyncSession,
    *,
    file_unique_id: str,
    source_channel_id: int,
    source_message_id: int,
    caption: str,
    detected_title: str | None,
    detected_episode: int | None,
    reason: str,
) -> PendingVideo | None:
    existing = await session.scalar(select(PendingVideo).where(PendingVideo.file_unique_id == file_unique_id))
    if existing is not None:
        return existing
    row = PendingVideo(
        file_unique_id=file_unique_id,
        source_channel_id=source_channel_id,
        source_message_id=source_message_id,
        caption=caption,
        detected_title=detected_title,
        detected_episode=detected_episode,
        reason=reason,
    )
    session.add(row)
    await session.flush()
    return row


async def remove_pending(session: AsyncSession, *, pending_id: int) -> int:
    result = await session.execute(delete(PendingVideo).where(PendingVideo.id == pending_id))
    return result.rowcount or 0


async def get_pending(session: AsyncSession, pending_id: int) -> PendingVideo | None:
    return await session.get(PendingVideo, pending_id)


async def list_pending(session: AsyncSession, limit: int = 50) -> list[PendingVideo]:
    result = await session.scalars(select(PendingVideo).order_by(PendingVideo.id.desc()).limit(limit))
    return list(result.all())


async def count_pending(session: AsyncSession) -> int:
    from sqlalchemy import func as sa_func

    row = await session.scalar(select(sa_func.count(PendingVideo.id)))
    return int(row or 0)
