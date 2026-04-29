"""Watcher mahalliy DB so'rovlari."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AutoReply,
    Channel,
    Exercise,
    ExerciseMedia,
    ForwardedFile,
    PendingVideo,
    Workout,
    WorkoutMedia,
    WorkoutReminder,
    WorkoutSchedule,
)

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


# ---------- Workout ----------


async def add_workout(
    session: AsyncSession,
    *,
    name: str,
    description: str,
    created_by: int,
) -> Workout:
    row = Workout(name=name, description=description, created_by=created_by, active=True)
    session.add(row)
    await session.flush()
    return row


async def get_workout(session: AsyncSession, workout_id: int) -> Workout | None:
    return await session.get(Workout, workout_id)


async def list_workouts(session: AsyncSession) -> list[Workout]:
    result = await session.scalars(select(Workout).order_by(Workout.id))
    return list(result.all())


async def remove_workout(session: AsyncSession, *, workout_id: int) -> int:
    ex_ids = [
        row[0]
        for row in (await session.execute(select(Exercise.id).where(Exercise.workout_id == workout_id))).all()
    ]
    if ex_ids:
        await session.execute(delete(ExerciseMedia).where(ExerciseMedia.exercise_id.in_(ex_ids)))
        await session.execute(delete(Exercise).where(Exercise.id.in_(ex_ids)))
    await session.execute(delete(WorkoutMedia).where(WorkoutMedia.workout_id == workout_id))
    await session.execute(delete(WorkoutSchedule).where(WorkoutSchedule.workout_id == workout_id))
    await session.execute(delete(WorkoutReminder).where(WorkoutReminder.workout_id == workout_id))
    result = await session.execute(delete(Workout).where(Workout.id == workout_id))
    return result.rowcount or 0


async def update_workout(
    session: AsyncSession,
    *,
    workout_id: int,
    name: str | None = None,
    description: str | None = None,
) -> Workout | None:
    row = await session.get(Workout, workout_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if description is not None:
        row.description = description
    await session.flush()
    return row


# ---------- WorkoutMedia ----------


async def add_workout_media(
    session: AsyncSession,
    *,
    workout_id: int,
    file_id: str,
    file_type: str,
    order_idx: int,
) -> WorkoutMedia:
    row = WorkoutMedia(workout_id=workout_id, file_id=file_id, file_type=file_type, order_idx=order_idx)
    session.add(row)
    await session.flush()
    return row


async def list_workout_media(session: AsyncSession, workout_id: int) -> list[WorkoutMedia]:
    result = await session.scalars(
        select(WorkoutMedia)
        .where(WorkoutMedia.workout_id == workout_id)
        .order_by(WorkoutMedia.order_idx, WorkoutMedia.id)
    )
    return list(result.all())


async def clear_workout_media(session: AsyncSession, workout_id: int) -> int:
    result = await session.execute(delete(WorkoutMedia).where(WorkoutMedia.workout_id == workout_id))
    return result.rowcount or 0


# ---------- WorkoutSchedule ----------


async def add_workout_schedule(
    session: AsyncSession,
    *,
    workout_id: int,
    days_mask: int,
    hour: int,
    minute: int,
    ack_timeout_min: int,
) -> WorkoutSchedule:
    row = WorkoutSchedule(
        workout_id=workout_id,
        days_mask=days_mask,
        hour=hour,
        minute=minute,
        ack_timeout_min=ack_timeout_min,
        active=True,
    )
    session.add(row)
    await session.flush()
    return row


async def get_workout_schedule(session: AsyncSession, schedule_id: int) -> WorkoutSchedule | None:
    return await session.get(WorkoutSchedule, schedule_id)


async def list_schedules_for_workout(session: AsyncSession, workout_id: int) -> list[WorkoutSchedule]:
    result = await session.scalars(
        select(WorkoutSchedule)
        .where(WorkoutSchedule.workout_id == workout_id)
        .order_by(WorkoutSchedule.hour, WorkoutSchedule.minute)
    )
    return list(result.all())


async def list_active_schedules(session: AsyncSession) -> list[WorkoutSchedule]:
    result = await session.scalars(
        select(WorkoutSchedule).where(WorkoutSchedule.active.is_(True)).order_by(WorkoutSchedule.id)
    )
    return list(result.all())


async def remove_workout_schedule(session: AsyncSession, *, schedule_id: int) -> int:
    result = await session.execute(delete(WorkoutSchedule).where(WorkoutSchedule.id == schedule_id))
    return result.rowcount or 0


async def toggle_workout_schedule(session: AsyncSession, *, schedule_id: int) -> WorkoutSchedule | None:
    row = await session.get(WorkoutSchedule, schedule_id)
    if row is None:
        return None
    row.active = not row.active
    await session.flush()
    return row


async def update_workout_schedule(
    session: AsyncSession,
    *,
    schedule_id: int,
    hour: int | None = None,
    minute: int | None = None,
    ack_timeout_min: int | None = None,
    days_mask: int | None = None,
) -> WorkoutSchedule | None:
    row = await session.get(WorkoutSchedule, schedule_id)
    if row is None:
        return None
    if hour is not None:
        row.hour = hour
    if minute is not None:
        row.minute = minute
    if ack_timeout_min is not None:
        row.ack_timeout_min = ack_timeout_min
    if days_mask is not None:
        row.days_mask = days_mask
    await session.flush()
    return row


# ---------- WorkoutReminder ----------


async def add_workout_reminder(
    session: AsyncSession,
    *,
    schedule_id: int,
    workout_id: int,
    chat_id: int,
    message_id: int | None,
) -> WorkoutReminder:
    row = WorkoutReminder(
        schedule_id=schedule_id,
        workout_id=workout_id,
        chat_id=chat_id,
        message_id=message_id,
    )
    session.add(row)
    await session.flush()
    return row


async def get_workout_reminder(session: AsyncSession, reminder_id: int) -> WorkoutReminder | None:
    return await session.get(WorkoutReminder, reminder_id)


async def update_reminder_status(
    session: AsyncSession,
    *,
    reminder_id: int,
    status: str,
    acked_at: datetime | None = None,
) -> WorkoutReminder | None:
    row = await session.get(WorkoutReminder, reminder_id)
    if row is None:
        return None
    row.status = status
    if acked_at is not None:
        row.acked_at = acked_at
    await session.flush()
    return row


async def update_reminder_message_id(session: AsyncSession, *, reminder_id: int, message_id: int) -> None:
    row = await session.get(WorkoutReminder, reminder_id)
    if row is None:
        return
    row.message_id = message_id
    await session.flush()


async def list_schedules_with_workouts(
    session: AsyncSession,
) -> list[tuple[WorkoutSchedule, Workout]]:
    """Return (schedule, workout) tuples for ALL schedules (active + paused)."""
    result = await session.execute(
        select(WorkoutSchedule, Workout)
        .join(Workout, WorkoutSchedule.workout_id == Workout.id)
        .order_by(WorkoutSchedule.hour, WorkoutSchedule.minute)
    )
    return [(row[0], row[1]) for row in result.all()]


# ---------- Exercise ----------


async def add_exercise(
    session: AsyncSession,
    *,
    workout_id: int,
    name: str,
    spec: str = "",
    description: str = "",
    order_idx: int | None = None,
) -> Exercise:
    if order_idx is None:
        existing = await session.scalars(select(Exercise.order_idx).where(Exercise.workout_id == workout_id))
        vals = list(existing.all())
        order_idx = (max(vals) + 1) if vals else 0
    row = Exercise(
        workout_id=workout_id,
        name=name,
        spec=spec,
        description=description,
        order_idx=order_idx,
    )
    session.add(row)
    await session.flush()
    return row


async def get_exercise(session: AsyncSession, exercise_id: int) -> Exercise | None:
    return await session.get(Exercise, exercise_id)


async def list_exercises(session: AsyncSession, workout_id: int) -> list[Exercise]:
    result = await session.scalars(
        select(Exercise).where(Exercise.workout_id == workout_id).order_by(Exercise.order_idx, Exercise.id)
    )
    return list(result.all())


async def update_exercise(
    session: AsyncSession,
    *,
    exercise_id: int,
    name: str | None = None,
    spec: str | None = None,
    description: str | None = None,
) -> Exercise | None:
    row = await session.get(Exercise, exercise_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if spec is not None:
        row.spec = spec
    if description is not None:
        row.description = description
    await session.flush()
    return row


async def remove_exercise(session: AsyncSession, *, exercise_id: int) -> int:
    await session.execute(delete(ExerciseMedia).where(ExerciseMedia.exercise_id == exercise_id))
    result = await session.execute(delete(Exercise).where(Exercise.id == exercise_id))
    return result.rowcount or 0


async def add_exercise_media(
    session: AsyncSession,
    *,
    exercise_id: int,
    file_id: str,
    file_type: str,
    order_idx: int = 0,
) -> ExerciseMedia:
    row = ExerciseMedia(
        exercise_id=exercise_id,
        file_id=file_id,
        file_type=file_type,
        order_idx=order_idx,
    )
    session.add(row)
    await session.flush()
    return row


async def list_exercise_media(session: AsyncSession, exercise_id: int) -> list[ExerciseMedia]:
    result = await session.scalars(
        select(ExerciseMedia)
        .where(ExerciseMedia.exercise_id == exercise_id)
        .order_by(ExerciseMedia.order_idx, ExerciseMedia.id)
    )
    return list(result.all())


async def clear_exercise_media(session: AsyncSession, exercise_id: int) -> int:
    result = await session.execute(delete(ExerciseMedia).where(ExerciseMedia.exercise_id == exercise_id))
    return result.rowcount or 0
