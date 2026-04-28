"""Hafta rejasi — kun-markazli ko'rinish.

Foydalanuvchi avval kunni tanlaydi (Du..Ya), so'ng o'sha kunga ulangan
mashqlarni ko'radi yoki yangi mashq ulaydi (mavjud mashqdan tanlash yoki
yangi mashq yaratish).
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.common import accessible, is_owner_callback, is_owner_message
from bot.keyboards import (
    days_label,
    week_day_view,
    week_overview,
    wizard_cancel,
    workout_media_done,
    workout_media_more,
    workout_picker,
)
from bot.services.workout_scheduler import WorkoutScheduler
from bot.states import WeekDayAddStates
from db.engine import AsyncSessionLocal
from db.models import (
    DOW_NAMES_UZ,
    MEDIA_ANIMATION,
    MEDIA_PHOTO,
    MEDIA_VIDEO,
)
from db.queries import (
    add_workout,
    add_workout_media,
    add_workout_schedule,
    list_schedules_with_workouts,
    list_workouts,
)

log = logging.getLogger(__name__)
router = Router(name="week")
router.message.filter(F.chat.type == "private")


# ---------- Week overview ----------


@router.callback_query(F.data == "menu:week")
async def cb_week(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await state.clear()
    counts = [0] * 7
    async with AsyncSessionLocal() as session:
        items = await list_schedules_with_workouts(session)
    for sch, _w in items:
        for i in range(7):
            if sch.days_mask & (1 << i):
                counts[i] += 1
    total = sum(counts)
    if total == 0:
        text = (
            "<b>📆 Hafta rejasi</b>\n\n" "Hozircha bironta jadval qo'shilmagan. Kun tanlang va mashq ulang."
        )
    else:
        text = f"<b>📆 Hafta rejasi</b>\n\nJami jadvallar: <b>{total}</b>"
    await msg.edit_text(text, reply_markup=week_overview(counts))
    await cb.answer()


# ---------- Day view ----------


@router.callback_query(F.data.startswith("week:day:"))
async def cb_day(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await state.clear()
    day_idx = int((cb.data or "").split(":")[-1])
    if not (0 <= day_idx <= 6):
        await cb.answer()
        return
    items = await _items_for_day(day_idx)
    name = DOW_NAMES_UZ[day_idx]
    if not items:
        text = f"<b>📆 {escape(name)}</b>\n\n" "Bu kunga jadval ulanmagan. Mashq ulashingiz mumkin."
    else:
        lines = [f"<b>📆 {escape(name)} — {len(items)} ta jadval</b>", ""]
        for sch, w in items:
            status = "🟢" if sch.active else "⚪"
            lines.append(
                f"{status} <b>{sch.hour:02d}:{sch.minute:02d}</b> — {escape(w.name)} "
                f"({sch.ack_timeout_min} daq)"
            )
        text = "\n".join(lines)
    await msg.edit_text(text, reply_markup=week_day_view(day_idx, items))
    await cb.answer()


async def _items_for_day(day_idx: int) -> list[tuple]:
    async with AsyncSessionLocal() as session:
        items = await list_schedules_with_workouts(session)
    return [(sch, w) for sch, w in items if sch.days_mask & (1 << day_idx)]


# ---------- Add workout to day ----------


@router.callback_query(F.data.startswith("week:add:"))
async def cb_add(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    day_idx = int((cb.data or "").split(":")[-1])
    if not (0 <= day_idx <= 6):
        await cb.answer()
        return
    async with AsyncSessionLocal() as session:
        workouts = await list_workouts(session)
    name = DOW_NAMES_UZ[day_idx]
    if not workouts:
        text = (
            f"<b>📆 {escape(name)}</b>\n\n" "Hozircha mashqlar yo'q. Yangi mashq yarating va shu kunga ulang."
        )
    else:
        text = f"<b>📆 {escape(name)} — Mashq ulash</b>\n\n" "Mavjud mashqdan tanlang yoki yangi yarating:"
    await msg.edit_text(text, reply_markup=workout_picker(workouts, day_idx))
    await cb.answer()


# ---------- Pick existing workout → time + timeout ----------


@router.callback_query(F.data.startswith("week:pick:"))
async def cb_pick(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    parts = (cb.data or "").split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    day_idx = int(parts[2])
    workout_id = int(parts[3])
    await state.set_state(WeekDayAddStates.waiting_for_time)
    await state.update_data(day_idx=day_idx, workout_id=workout_id, mode="existing")
    name = DOW_NAMES_UZ[day_idx]
    await msg.edit_text(
        f"<b>📆 {escape(name)}</b>\n\n"
        "Vaqtni <b>HH:MM</b> formatida yuboring (mas. <code>09:00</code> yoki <code>18:30</code>):",
        reply_markup=wizard_cancel(),
    )
    await cb.answer()


# ---------- Create new workout from week flow ----------


@router.callback_query(F.data.startswith("week:newwo:"))
async def cb_newwo(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    day_idx = int((cb.data or "").split(":")[-1])
    if not (0 <= day_idx <= 6):
        await cb.answer()
        return
    await state.set_state(WeekDayAddStates.waiting_for_new_name)
    await state.update_data(day_idx=day_idx, mode="new", media=[])
    name = DOW_NAMES_UZ[day_idx]
    await msg.edit_text(
        f"<b>📆 {escape(name)} — Yangi mashq</b>\n\n" "Mashq nomini yuboring (mas. <code>Yuz mashqi</code>):",
        reply_markup=wizard_cancel(),
    )
    await cb.answer()


@router.message(WeekDayAddStates.waiting_for_new_name)
async def m_new_name(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 128:
        await message.answer("Nom 1-128 belgi orasida bo'lsin. Qayta yuboring:")
        return
    await state.update_data(name=name)
    await state.set_state(WeekDayAddStates.waiting_for_new_description)
    await message.answer(
        "Tavsif (set/reps va bajarish usuli) yuboring:",
        reply_markup=wizard_cancel(),
    )


@router.message(WeekDayAddStates.waiting_for_new_description)
async def m_new_desc(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    desc = (message.text or "").strip()
    await state.update_data(description=desc, media=[])
    await state.set_state(WeekDayAddStates.waiting_for_new_media)
    await message.answer(
        "Endi rasm/video yuboring (bir nechta bo'lishi mumkin).\n"
        "Tugatgach <b>✅ Saqlash</b> tugmasini bosing yoki mediasiz tugatish uchun pastdagi tugmani.",
        reply_markup=workout_media_done(),
    )


@router.message(WeekDayAddStates.waiting_for_new_media, F.photo | F.video | F.animation)
async def m_new_media(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    file_id: str | None = None
    file_type = MEDIA_PHOTO
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
        f"Qabul qilindi. Jami media: <b>{len(media)}</b>.",
        reply_markup=workout_media_more(),
    )


@router.callback_query(F.data.in_({"wo:media:none", "wo:media:save"}), WeekDayAddStates.waiting_for_new_media)
async def cb_new_media_done(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
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
    await state.update_data(workout_id=workout_id)
    await state.set_state(WeekDayAddStates.waiting_for_time)
    day_idx = int(data.get("day_idx", 0))
    day_name = DOW_NAMES_UZ[day_idx]
    await msg.edit_text(
        f"<b>📆 {escape(day_name)} — {escape(name)}</b>\n\n"
        "Mashq saqlandi. Endi vaqtni <b>HH:MM</b> formatida yuboring (mas. <code>09:00</code>):",
        reply_markup=wizard_cancel(),
    )
    await cb.answer("Saqlandi")


# ---------- Time + timeout (shared by existing/new) ----------


@router.message(WeekDayAddStates.waiting_for_time)
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
    await state.set_state(WeekDayAddStates.waiting_for_timeout)
    await message.answer(
        f"Vaqt: <b>{hour:02d}:{minute:02d}</b>\n\n"
        "Necha daqiqada javob kutilsin? (raqam, 1-240, mas. <code>10</code>):",
        reply_markup=wizard_cancel(),
    )


@router.message(WeekDayAddStates.waiting_for_timeout)
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
    day_idx = int(data["day_idx"])
    hour = int(data["hour"])
    minute = int(data["minute"])
    days_mask = 1 << day_idx
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
    day_name = DOW_NAMES_UZ[day_idx]
    await message.answer(
        f"✅ Jadval qo'shildi: <b>{escape(day_name)} {hour:02d}:{minute:02d}</b> "
        f"(javob kutish: {n} daq)\n\n"
        f"<i>{days_label(days_mask)} kuniga ulandi.</i>"
    )
