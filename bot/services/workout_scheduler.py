"""Mashqlar uchun APScheduler asosida eslatma servisi.

- Bot startup: barcha aktiv jadvallar yuklanadi va CRON triggerga qo'shiladi.
- Vaqti kelganda: mashq nomi/tavsifi + media + 3 ta ack tugma yuboriladi.
- N daqiqa javob bo'lmasa: ehtiyotsiz so'kishli xabar yuboriladi.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.services.scolds import random_scold
from config import settings
from db.models import (
    DOW_CRON,
    MEDIA_ANIMATION,
    MEDIA_VIDEO,
    REM_PENDING,
    REM_SCOLDED,
    WorkoutSchedule,
)
from db.queries import (
    add_workout_reminder,
    get_workout,
    get_workout_reminder,
    get_workout_schedule,
    list_active_schedules,
    list_exercise_media,
    list_exercises,
    list_workout_media,
    update_reminder_message_id,
    update_reminder_status,
)

log = logging.getLogger(__name__)

# Job-ID conventions:
#   workout-schedule-{schedule_id}     — recurring CRON job
#   workout-scold-{reminder_id}        — one-shot scold job


def _job_schedule(schedule_id: int) -> str:
    return f"workout-schedule-{schedule_id}"


def _job_scold(reminder_id: int) -> str:
    return f"workout-scold-{reminder_id}"


def _ack_keyboard(reminder_id: int):  # type: ignore[no-untyped-def]
    """Inline keyboard for ack buttons."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅Bajardim", callback_data=f"wo:ack:{reminder_id}:done"),
                InlineKeyboardButton(text="⏭Keyinroq", callback_data=f"wo:ack:{reminder_id}:snooze"),
                InlineKeyboardButton(text="❌Skip", callback_data=f"wo:ack:{reminder_id}:skip"),
            ]
        ]
    )


class WorkoutScheduler:
    """Manages all scheduled workout reminders.

    Lifecycle: instantiate, then call ``start()`` once on app boot.
    Use ``add_schedule`` / ``remove_schedule`` when admin changes schedules.
    """

    def __init__(
        self,
        *,
        bot: Bot,
        session_factory: async_sessionmaker,
        owner_id: int,
        timezone: str | None = None,
    ) -> None:
        self.bot = bot
        self.session_factory = session_factory
        self.owner_id = owner_id
        self.tz = timezone or settings.WORKOUT_TZ
        self.scheduler = AsyncIOScheduler(timezone=self.tz)

    async def start(self) -> None:
        async with self.session_factory() as session:
            schedules = await list_active_schedules(session)
        for sch in schedules:
            self._register(sch)
        self.scheduler.start()
        log.info("Workout scheduler started: %d schedules (tz=%s)", len(schedules), self.tz)

    async def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    # ---------- Schedule management ----------

    def _register(self, schedule: WorkoutSchedule) -> None:
        days = [DOW_CRON[i] for i in range(7) if schedule.days_mask & (1 << i)]
        if not days:
            log.warning("Schedule %d has empty days_mask, skipping", schedule.id)
            return
        trigger = CronTrigger(
            day_of_week=",".join(days),
            hour=schedule.hour,
            minute=schedule.minute,
            timezone=self.tz,
        )
        self.scheduler.add_job(
            self._fire_reminder,
            trigger=trigger,
            args=[schedule.id],
            id=_job_schedule(schedule.id),
            replace_existing=True,
            misfire_grace_time=60,
        )
        log.info(
            "Scheduled workout: id=%d days=%s time=%02d:%02d tz=%s",
            schedule.id,
            ",".join(days),
            schedule.hour,
            schedule.minute,
            self.tz,
        )

    def add_schedule(self, schedule: WorkoutSchedule) -> None:
        self._register(schedule)

    def remove_schedule(self, schedule_id: int) -> None:
        with contextlib.suppress(Exception):
            self.scheduler.remove_job(_job_schedule(schedule_id))

    # ---------- Reminder firing ----------

    async def _fire_reminder(self, schedule_id: int) -> None:
        try:
            async with self.session_factory() as session:
                schedule = await get_workout_schedule(session, schedule_id)
                if schedule is None or not schedule.active:
                    return
                workout = await get_workout(session, schedule.workout_id)
                if workout is None or not workout.active:
                    return
                media = await list_workout_media(session, workout.id)
                exercises = await list_exercises(session, workout.id)
                exercise_payload: list[tuple[str, list[tuple[str, str]]]] = []
                for ex in exercises:
                    ex_media = await list_exercise_media(session, ex.id)
                    exercise_payload.append(
                        (
                            _format_exercise_line(ex.name, ex.spec),
                            [(m.file_id, m.file_type) for m in ex_media],
                        )
                    )
                reminder = await add_workout_reminder(
                    session,
                    schedule_id=schedule.id,
                    workout_id=workout.id,
                    chat_id=self.owner_id,
                    message_id=None,
                )
                await session.commit()
                reminder_id = reminder.id
                workout_name = workout.name
                workout_desc = workout.description
                ack_timeout = schedule.ack_timeout_min

            text = _format_workout_text_safe(
                workout_name,
                workout_desc,
                [line for line, _ in exercise_payload],
            )
            kb = _ack_keyboard(reminder_id)

            sent_message_id: int | None = None
            try:
                if media:
                    first = media[0]
                    if first.file_type == MEDIA_VIDEO:
                        msg = await self.bot.send_video(
                            chat_id=self.owner_id,
                            video=first.file_id,
                            caption=text,
                            reply_markup=kb,
                        )
                    elif first.file_type == MEDIA_ANIMATION:
                        msg = await self.bot.send_animation(
                            chat_id=self.owner_id,
                            animation=first.file_id,
                            caption=text,
                            reply_markup=kb,
                        )
                    else:
                        msg = await self.bot.send_photo(
                            chat_id=self.owner_id,
                            photo=first.file_id,
                            caption=text,
                            reply_markup=kb,
                        )
                    sent_message_id = msg.message_id
                    for extra in media[1:]:
                        try:
                            if extra.file_type == MEDIA_VIDEO:
                                await self.bot.send_video(self.owner_id, extra.file_id)
                            elif extra.file_type == MEDIA_ANIMATION:
                                await self.bot.send_animation(self.owner_id, extra.file_id)
                            else:
                                await self.bot.send_photo(self.owner_id, extra.file_id)
                        except TelegramAPIError:
                            log.exception("Failed to send extra media for workout %d", workout.id)
                else:
                    msg = await self.bot.send_message(self.owner_id, text, reply_markup=kb)
                    sent_message_id = msg.message_id

                # Send each exercise's media as follow-ups (caption = exercise line).
                for ex_line, ex_media_pairs in exercise_payload:
                    for idx, (file_id, file_type) in enumerate(ex_media_pairs):
                        caption = ex_line if idx == 0 else None
                        try:
                            if file_type == MEDIA_VIDEO:
                                await self.bot.send_video(self.owner_id, file_id, caption=caption)
                            elif file_type == MEDIA_ANIMATION:
                                await self.bot.send_animation(self.owner_id, file_id, caption=caption)
                            else:
                                await self.bot.send_photo(self.owner_id, file_id, caption=caption)
                        except TelegramAPIError:
                            log.exception("Failed to send exercise media for workout %d", workout.id)
            except TelegramAPIError:
                log.exception("Failed to send reminder for schedule %d", schedule_id)

            if sent_message_id is not None:
                async with self.session_factory() as session:
                    await update_reminder_message_id(
                        session, reminder_id=reminder_id, message_id=sent_message_id
                    )
                    await session.commit()

            self._schedule_scold(reminder_id, ack_timeout)
        except Exception:
            log.exception("_fire_reminder crashed for schedule_id=%s", schedule_id)

    def _schedule_scold(self, reminder_id: int, timeout_min: int) -> None:
        from datetime import timedelta

        run_at = datetime.now(self.scheduler.timezone) + timedelta(minutes=max(1, timeout_min))
        self.scheduler.add_job(
            self._fire_scold,
            trigger=DateTrigger(run_date=run_at, timezone=self.tz),
            args=[reminder_id],
            id=_job_scold(reminder_id),
            replace_existing=True,
            misfire_grace_time=120,
        )

    def cancel_scold(self, reminder_id: int) -> None:
        with contextlib.suppress(Exception):
            self.scheduler.remove_job(_job_scold(reminder_id))

    def reschedule_scold(self, reminder_id: int, timeout_min: int) -> None:
        self._schedule_scold(reminder_id, timeout_min)

    async def _fire_scold(self, reminder_id: int) -> None:
        try:
            async with self.session_factory() as session:
                rem = await get_workout_reminder(session, reminder_id)
                if rem is None or rem.status != REM_PENDING:
                    return
                workout = await get_workout(session, rem.workout_id)
                await update_reminder_status(session, reminder_id=reminder_id, status=REM_SCOLDED)
                await session.commit()

            text = (
                f"<b>⚠ Tanbex!</b>\n\n"
                f"<i>{random_scold()}</i>\n\n"
                f"Mashq: <b>{workout.name if workout else '—'}</b>"
            )
            try:
                await self.bot.send_message(self.owner_id, text)
            except TelegramAPIError:
                log.exception("Failed to send scold for reminder %d", reminder_id)
        except Exception:
            log.exception("_fire_scold crashed for reminder_id=%s", reminder_id)


def _format_exercise_line(name: str, spec: str) -> str:
    """Single exercise summary line for reminder message."""
    from html import escape

    spec_part = f" — <i>{escape(spec)}</i>" if spec else ""
    return f"<b>{escape(name)}</b>{spec_part}"


def _format_workout_text_safe(name: str, description: str, exercises: list[str] | None = None) -> str:
    """HTML-safe formatter (without DB session)."""
    from html import escape

    parts = [f"<b>💪 {escape(name)}</b>"]
    if description:
        parts.append("")
        parts.append(escape(description))
    if exercises:
        parts.append("")
        parts.append("<b>📋 Mashqlar:</b>")
        for i, line in enumerate(exercises, start=1):
            parts.append(f"{i}. {line}")
    parts.append("")
    parts.append("<i>Vaqtida javob bermasangiz — tanbex bor!</i>")
    return "\n".join(parts)
