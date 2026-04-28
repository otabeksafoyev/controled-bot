"""Mashqlar (workout scheduler) menyu va FSM handlerlari."""

from __future__ import annotations

import logging
from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.common import accessible, is_owner_callback, is_owner_message
from bot.keyboards import (
    days_label,
    days_picker,
    schedule_detail,
    schedules_list,
    wizard_cancel,
    workout_delete_confirm,
    workout_detail,
    workout_media_done,
    workout_media_more,
    workouts_list,
)
from bot.services.workout_scheduler import WorkoutScheduler
from bot.states import AddScheduleStates, AddWorkoutStates
from db.engine import AsyncSessionLocal
from db.models import (
    MEDIA_ANIMATION,
    MEDIA_PHOTO,
    MEDIA_VIDEO,
    REM_DONE,
    REM_PENDING,
    REM_SKIPPED,
)
from db.queries import (
    add_workout,
    add_workout_media,
    add_workout_schedule,
    get_workout,
    get_workout_reminder,
    get_workout_schedule,
    list_schedules_for_workout,
    list_workout_media,
    list_workouts,
    remove_workout,
    remove_workout_schedule,
    toggle_workout_schedule,
    update_reminder_status,
)

log = logging.getLogger(__name__)
router = Router(name="workouts")
router.message.filter(F.chat.type == "private")


def _format_workout_view(name: str, description: str, n_media: int, n_schedules: int) -> str:
    parts = [f"<b>💪 {escape(name)}</b>"]
    if description:
        parts.append("")
        parts.append(escape(description))
    parts.append("")
    parts.append(f"📎 Media: <b>{n_media}</b>")
    parts.append(f"📅 Jadvallar: <b>{n_schedules}</b>")
    return "\n".join(parts)


# ---------- Workouts list ----------


@router.callback_query(F.data == "menu:workouts")
async def cb_workouts(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await state.clear()
    async with AsyncSessionLocal() as session:
        items = await list_workouts(session)
    if not items:
        text = (
            "<b>💪 Mashqlar</b>\n\n"
            "Hozircha mashq qo'shilmagan. Yangi mashq qo'shing — keyin unga jadval ulang."
        )
    else:
        text = f"<b>💪 Mashqlar</b>\n\nJami: <b>{len(items)}</b>"
    await msg.edit_text(text, reply_markup=workouts_list(items))
    await cb.answer()


# ---------- Add workout wizard ----------


@router.callback_query(F.data == "wo:add")
async def cb_add(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await state.set_state(AddWorkoutStates.waiting_for_name)
    await msg.edit_text(
        "<b>Yangi mashq</b>\n\nMashq nomini yuboring (mas. <code>Yuz mashqi</code>):",
        reply_markup=wizard_cancel(),
    )
    await cb.answer()


@router.message(AddWorkoutStates.waiting_for_name)
async def m_name(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 128:
        await message.answer("Nom 1-128 belgi orasida bo'lsin. Qayta yuboring:")
        return
    await state.update_data(name=name)
    await state.set_state(AddWorkoutStates.waiting_for_description)
    await message.answer(
        "Tavsif (set/reps va bajarish usuli) yuboring.\n"
        "Masalan: <code>3 set × 15 takror, asta-sekin pastga tushing</code>",
        reply_markup=wizard_cancel(),
    )


@router.message(AddWorkoutStates.waiting_for_description)
async def m_desc(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    desc = (message.text or "").strip()
    await state.update_data(description=desc, media=[])
    await state.set_state(AddWorkoutStates.waiting_for_media)
    await message.answer(
        "Endi rasm/video yuboring (bir nechta bo'lishi mumkin).\n"
        "Tugatgach <b>✅ Saqlash</b> tugmasini bosing yoki mediasiz tugatish uchun pastdagi tugmani.",
        reply_markup=workout_media_done(),
    )


@router.message(AddWorkoutStates.waiting_for_media, F.photo | F.video | F.animation)
async def m_media(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    file_id: str | None = None
    file_type: str = MEDIA_PHOTO
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = MEDIA_PHOTO
    elif message.video:
        file_id = message.video.file_id
        file_type = MEDIA_VIDEO
    elif message.animation:
        file_id = message.animation.file_id
        file_type = MEDIA_ANIMATION
    if not file_id:
        return
    data = await state.get_data()
    media: list[dict] = list(data.get("media", []))
    media.append({"file_id": file_id, "file_type": file_type})
    await state.update_data(media=media)
    await message.answer(
        f"Qabul qilindi. Jami media: <b>{len(media)}</b>. Yana yuborishingiz yoki saqlashingiz mumkin.",
        reply_markup=workout_media_more(),
    )


@router.callback_query(F.data == "wo:media:none", AddWorkoutStates.waiting_for_media)
async def cb_media_none(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    await _save_workout(cb, state)


@router.callback_query(F.data == "wo:media:save", AddWorkoutStates.waiting_for_media)
async def cb_media_save(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    await _save_workout(cb, state)


async def _save_workout(cb: CallbackQuery, state: FSMContext) -> None:
    msg = accessible(cb)
    if msg is None:
        return
    data = await state.get_data()
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    media: list[dict] = data.get("media", [])
    if not name:
        await cb.answer("Nom yo'q", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        workout = await add_workout(
            session,
            name=name,
            description=description,
            created_by=cb.from_user.id if cb.from_user else 0,
        )
        for idx, m in enumerate(media):
            await add_workout_media(
                session,
                workout_id=workout.id,
                file_id=m["file_id"],
                file_type=m["file_type"],
                order_idx=idx,
            )
        await session.commit()
        workout_id = workout.id
    await state.clear()
    await _show_workout(cb, workout_id)


# ---------- Workout view ----------


@router.callback_query(F.data.startswith("wo:view:"))
async def cb_view(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    await state.clear()
    workout_id = int((cb.data or "").split(":")[-1])
    await _show_workout(cb, workout_id)


async def _show_workout(cb: CallbackQuery, workout_id: int) -> None:
    msg = accessible(cb)
    if msg is None:
        return
    async with AsyncSessionLocal() as session:
        workout = await get_workout(session, workout_id)
        if workout is None:
            await cb.answer("Topilmadi", show_alert=True)
            return
        media = await list_workout_media(session, workout_id)
        schedules = await list_schedules_for_workout(session, workout_id)
    text = _format_workout_view(workout.name, workout.description, len(media), len(schedules))
    await msg.edit_text(text, reply_markup=workout_detail(workout_id, has_schedules=bool(schedules)))
    await cb.answer()


@router.callback_query(F.data.startswith("wo:delask:"))
async def cb_delask(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    workout_id = int((cb.data or "").split(":")[-1])
    await msg.edit_text(
        "Mashqni o'chirishni tasdiqlaysizmi? Barcha jadvallar va media ham o'chadi.",
        reply_markup=workout_delete_confirm(workout_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("wo:delok:"))
async def cb_delok(cb: CallbackQuery, scheduler: WorkoutScheduler) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    workout_id = int((cb.data or "").split(":")[-1])
    async with AsyncSessionLocal() as session:
        scheds = await list_schedules_for_workout(session, workout_id)
        for s in scheds:
            scheduler.remove_schedule(s.id)
        await remove_workout(session, workout_id=workout_id)
        await session.commit()
    await msg.edit_text("Mashq o'chirildi.")
    await cb.answer("O'chirildi")


# ---------- Schedules list ----------


@router.callback_query(F.data.startswith("wo:scheds:"))
async def cb_scheds(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await state.clear()
    workout_id = int((cb.data or "").split(":")[-1])
    async with AsyncSessionLocal() as session:
        workout = await get_workout(session, workout_id)
        scheds = await list_schedules_for_workout(session, workout_id)
    if workout is None:
        await cb.answer("Topilmadi", show_alert=True)
        return
    if not scheds:
        text = (
            f"<b>📅 Jadvallar — {escape(workout.name)}</b>\n\n" "Hozircha jadval yo'q. Yangi jadval qo'shing."
        )
    else:
        text = f"<b>📅 Jadvallar — {escape(workout.name)}</b>\n\nJami: <b>{len(scheds)}</b>"
    await msg.edit_text(text, reply_markup=schedules_list(workout_id, scheds))
    await cb.answer()


# ---------- Add schedule wizard ----------


@router.callback_query(F.data.startswith("wo:schedadd:"))
async def cb_schedadd(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    workout_id = int((cb.data or "").split(":")[-1])
    await state.set_state(AddScheduleStates.waiting_for_days)
    await state.update_data(workout_id=workout_id, days_mask=0)
    await msg.edit_text(
        "<b>Yangi jadval</b>\n\nKunlarni tanlang (bir nechta), so'ng ✔️ Tasdiq:",
        reply_markup=days_picker(0),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("wo:dtoggle:"), AddScheduleStates.waiting_for_days)
async def cb_dtoggle(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    idx = int((cb.data or "").split(":")[-1])
    data = await state.get_data()
    mask = int(data.get("days_mask", 0)) ^ (1 << idx)
    await state.update_data(days_mask=mask)
    await msg.edit_reply_markup(reply_markup=days_picker(mask))
    await cb.answer()


@router.callback_query(F.data == "wo:dconfirm", AddScheduleStates.waiting_for_days)
async def cb_dconfirm(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    data = await state.get_data()
    mask = int(data.get("days_mask", 0))
    if mask == 0:
        await cb.answer("Hech bo'lmasa 1 ta kun tanlang", show_alert=True)
        return
    await state.set_state(AddScheduleStates.waiting_for_time)
    await msg.edit_text(
        f"Tanlangan kunlar: <b>{days_label(mask)}</b>\n\n"
        "Endi vaqtni <b>HH:MM</b> formatida yuboring (mas. <code>09:00</code> yoki <code>18:30</code>):",
        reply_markup=wizard_cancel(),
    )
    await cb.answer()


@router.message(AddScheduleStates.waiting_for_time)
async def m_time(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    text = (message.text or "").strip()
    try:
        hh_str, mm_str = text.split(":")
        hour = int(hh_str)
        minute = int(mm_str)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("Format noto'g'ri. <b>HH:MM</b> ko'rinishida yuboring (mas. 09:00):")
        return
    await state.update_data(hour=hour, minute=minute)
    await state.set_state(AddScheduleStates.waiting_for_timeout)
    await message.answer(
        f"Vaqt: <b>{hour:02d}:{minute:02d}</b>\n\n"
        "Necha daqiqada javob kutilsin? (raqam yuboring, mas. <code>10</code>; minimum 1, maksimum 240)",
        reply_markup=wizard_cancel(),
    )


@router.message(AddScheduleStates.waiting_for_timeout)
async def m_timeout(message: Message, state: FSMContext, scheduler: WorkoutScheduler) -> None:
    if not is_owner_message(message):
        return
    text = (message.text or "").strip()
    try:
        n = int(text)
        if not (1 <= n <= 240):
            raise ValueError
    except ValueError:
        await message.answer("Raqam 1-240 oraliqda bo'lsin. Qayta yuboring:")
        return
    data = await state.get_data()
    workout_id = int(data["workout_id"])
    days_mask = int(data["days_mask"])
    hour = int(data["hour"])
    minute = int(data["minute"])
    async with AsyncSessionLocal() as session:
        sch = await add_workout_schedule(
            session,
            workout_id=workout_id,
            days_mask=days_mask,
            hour=hour,
            minute=minute,
            ack_timeout_min=n,
        )
        await session.commit()
        scheduler.add_schedule(sch)
    await state.clear()
    await message.answer(
        f"✅ Jadval qo'shildi: <b>{days_label(days_mask)} {hour:02d}:{minute:02d}</b> "
        f"(javob kutish: {n} daq)"
    )


# ---------- Schedule detail / toggle / delete ----------


@router.callback_query(F.data.startswith("wo:sched:"))
async def cb_sched_detail(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    schedule_id = int((cb.data or "").split(":")[-1])
    async with AsyncSessionLocal() as session:
        sch = await get_workout_schedule(session, schedule_id)
        if sch is None:
            await cb.answer("Topilmadi", show_alert=True)
            return
        workout = await get_workout(session, sch.workout_id)
    text = (
        f"<b>📅 Jadval</b>\n\n"
        f"Mashq: <b>{escape(workout.name) if workout else '—'}</b>\n"
        f"Kunlar: <b>{days_label(sch.days_mask)}</b>\n"
        f"Vaqt: <b>{sch.hour:02d}:{sch.minute:02d}</b>\n"
        f"Javob kutish: <b>{sch.ack_timeout_min} daq</b>\n"
        f"Holati: <b>{'faol' if sch.active else 'pauza'}</b>"
    )
    await msg.edit_text(text, reply_markup=schedule_detail(sch.id, sch.workout_id, sch.active))
    await cb.answer()


@router.callback_query(F.data.startswith("wo:schedtoggle:"))
async def cb_sched_toggle(cb: CallbackQuery, scheduler: WorkoutScheduler) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    schedule_id = int((cb.data or "").split(":")[-1])
    async with AsyncSessionLocal() as session:
        sch = await toggle_workout_schedule(session, schedule_id=schedule_id)
        if sch is None:
            await cb.answer("Topilmadi", show_alert=True)
            return
        await session.commit()
        workout = await get_workout(session, sch.workout_id)
        if sch.active:
            scheduler.add_schedule(sch)
        else:
            scheduler.remove_schedule(sch.id)
    text = (
        f"<b>📅 Jadval</b>\n\n"
        f"Mashq: <b>{escape(workout.name) if workout else '—'}</b>\n"
        f"Kunlar: <b>{days_label(sch.days_mask)}</b>\n"
        f"Vaqt: <b>{sch.hour:02d}:{sch.minute:02d}</b>\n"
        f"Javob kutish: <b>{sch.ack_timeout_min} daq</b>\n"
        f"Holati: <b>{'faol' if sch.active else 'pauza'}</b>"
    )
    await msg.edit_text(text, reply_markup=schedule_detail(sch.id, sch.workout_id, sch.active))
    await cb.answer("Yangilandi")


@router.callback_query(F.data.startswith("wo:scheddel:"))
async def cb_sched_del(cb: CallbackQuery, scheduler: WorkoutScheduler, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    schedule_id = int((cb.data or "").split(":")[-1])
    async with AsyncSessionLocal() as session:
        sch = await get_workout_schedule(session, schedule_id)
        if sch is None:
            await cb.answer("Topilmadi", show_alert=True)
            return
        workout_id = sch.workout_id
        await remove_workout_schedule(session, schedule_id=schedule_id)
        await session.commit()
    scheduler.remove_schedule(schedule_id)
    await cb.answer("O'chirildi")
    await state.clear()
    async with AsyncSessionLocal() as session:
        workout = await get_workout(session, workout_id)
        scheds = await list_schedules_for_workout(session, workout_id)
    if workout is None:
        await msg.edit_text("Mashq topilmadi.", reply_markup=workouts_list([]))
        return
    if not scheds:
        text = (
            f"<b>📅 Jadvallar — {escape(workout.name)}</b>\n\n" "Hozircha jadval yo'q. Yangi jadval qo'shing."
        )
    else:
        text = f"<b>📅 Jadvallar — {escape(workout.name)}</b>\n\nJami: <b>{len(scheds)}</b>"
    await msg.edit_text(text, reply_markup=schedules_list(workout_id, scheds))


# ---------- Reminder ack ----------


@router.callback_query(F.data.startswith("wo:ack:"))
async def cb_ack(cb: CallbackQuery, scheduler: WorkoutScheduler) -> None:
    if not is_owner_callback(cb):
        return
    parts = (cb.data or "").split(":")
    if len(parts) < 4:
        await cb.answer()
        return
    reminder_id = int(parts[2])
    action = parts[3]

    async with AsyncSessionLocal() as session:
        rem = await get_workout_reminder(session, reminder_id)
        if rem is None:
            await cb.answer("Eslatma topilmadi", show_alert=True)
            return
        if rem.status != REM_PENDING:
            await cb.answer("Bu eslatma allaqachon yopilgan", show_alert=True)
            return

        if action == "done":
            await update_reminder_status(
                session, reminder_id=reminder_id, status=REM_DONE, acked_at=datetime.utcnow()
            )
            await session.commit()
            scheduler.cancel_scold(reminder_id)
            await _strip_buttons(cb, "✅ Bajarildi! Yashang!")
            await cb.answer("Yashang!")
            return
        if action == "snooze":
            await session.commit()
            scheduler.cancel_scold(reminder_id)
            from config import settings as _s

            scheduler.reschedule_scold(reminder_id, _s.WORKOUT_SNOOZE_MIN)
            await _strip_buttons(
                cb, f"⏭ Keyinroq tanlandi. {_s.WORKOUT_SNOOZE_MIN} daqiqadan keyin tanbex bor."
            )
            await cb.answer("Keyinroq")
            return
        if action == "skip":
            await update_reminder_status(
                session, reminder_id=reminder_id, status=REM_SKIPPED, acked_at=datetime.utcnow()
            )
            await session.commit()
            scheduler.cancel_scold(reminder_id)
            await _strip_buttons(cb, "❌ O'tkazib yuborildi.")
            await cb.answer("Skip")
            return

    await cb.answer()


async def _strip_buttons(cb: CallbackQuery, suffix: str) -> None:
    msg = accessible(cb)
    if msg is None:
        return
    try:
        if msg.caption is not None:
            new_caption = (msg.caption or "") + f"\n\n<i>{escape(suffix)}</i>"
            await msg.edit_caption(caption=new_caption, reply_markup=None)
        else:
            new_text = (msg.text or "") + f"\n\n<i>{escape(suffix)}</i>"
            await msg.edit_text(new_text, reply_markup=None)
    except Exception:
        log.exception("Failed to strip buttons")
