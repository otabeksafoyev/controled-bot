"""Tayyor mashq rejalarini import qilish handlerlari.

'Otabek — Life OS 2026' rejasidan 7 kunlik mashqlar (33 ta element) bir tugma
bilan DB-ga import qilinadi. Import yakunida foydalanuvchi har kunga vaqt
(HH:MM) kiritadi va o'sha kun maskali jadval avtomatik yaratiladi.
"""

from __future__ import annotations

import logging
import re
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.common import accessible, is_owner_callback, is_owner_message
from bot.services.workout_scheduler import WorkoutScheduler
from bot.states import ImportTimesStates
from config import settings
from db.engine import AsyncSessionLocal
from db.models import DOW_NAMES_UZ
from db.queries import (
    add_exercise,
    add_workout,
    add_workout_schedule,
    list_workouts,
)

log = logging.getLogger(__name__)
router = Router(name="seed")

# 7-day plan: list element index = day-of-week index (0=Du..6=Ya).
# Tuple: (workout_name, description, tip_id, exercises[]).
OTABEK_PLAN: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    (
        "Du — Ko'krak + Biceps",
        "Ko'krak + Biceps. Har repda 3 sek sekin tushish, oxirgi set charchagunga qadar.",
        "tip:chest",
        [
            ("Wide Push-up", "4×12", "Qo'llar yelkadan kengroq. Pastda ko'krakni to'liq cho'zish."),
            ("Incline Push-up", "4×15", "Qo'llar stul/javonga ko'tarilgan. Yuqori ko'krakka."),
            ("Decline Push-up", "4×10", "Oyoqlar ko'tarilgan. Quyi ko'krak va old deltoid."),
            ("Table Inverted Row", "4×maks", "Stol ostida, ko'krakni chetiga tortish."),
            ("Hammer Curl", "4×15", "Suv shishasi. Neytral ushlab tutish, sekin temp."),
        ],
    ),
    (
        "Se — Yelka (V-shakl)",
        "V-shakl kuni. 2 sek yuqori / 3 sek quyi. Lateral raise eng muhim.",
        "tip:shoulders",
        [
            ("Pike Push-up", "5×12", "Sonlar yuqori, bosh yerga qarab. To'g'ri yelka pressi."),
            ("Wall Handstand Hold", "4×30s", "Qo'llar devordan 30 sm. Maksimal vaqt ushla."),
            ("Lateral Raise", "5×20", "1.5L suv shishasi. 2 sek yuqori / 3 sek quyi."),
            ("Front Raise", "4×15", "Ko'z darajasigacha ko'taring."),
            ("Shoulder Tap", "4×30", "Push-up holatida, almashinib yelkani teping."),
        ],
    ),
    (
        "Ch — Orqa (Kenglik)",
        "Orqa — kenglik. Har tortishda ko'krakni oldinga.",
        "tip:back",
        [
            ("Table Inverted Row", "5×maks", "To'liq kenglik. Ko'krak yuqori, kuraklar siqilsin."),
            ("Doorway Row", "4×15", "Eshik qoqasini ushlab, orqaga eging, torting."),
            ("Superman Hold", "4×45s", "Yuzi pastga, qo'l va oyoqlarni bir vaqtda ko'taring."),
            ("Reverse Snow Angel", "4×30", "Yuzi pastga, qo'llar qor farishtasi shaklida."),
            ("Wall Y-Raise", "4×15", "Devorga yuzlaning, qo'llarni Y shakliga."),
        ],
    ),
    (
        "Pa — Core & Qorin",
        "Core & Qorin. Vacuum = tor bel uchun #1 mashq.",
        "tip:core",
        [
            ("Hanging Knee Raise", "4×15", "Eshik qoqasidan osilib, tizzalarni ko'krakka."),
            ("Slow Crunch", "4×25", "3 sek yuqori, 3 sek quyi. Har tolani his qiling."),
            ("Plank", "4×90s", "To'g'ri chiziq. Son sagmasin."),
            ("Stomach Vacuum", "4×45s", "To'liq nafas chiqaring, kindikni orqamiqqa torting."),
            ("Dragon Flag Negative", "3×5", "Tepadan sekin tushing. To'liq tana tarangligi."),
        ],
    ),
    (
        "Ju — Oyoq (Testosteron)",
        "Oyoq — testosteron kuni. Oyoq mashqi testosteronni oshiradi.",
        "tip:legs",
        [
            ("Bodyweight Squat", "5×30", "3 sek tushish. Oxirgi set 5 sek sekin."),
            ("Bulgarian Split Squat", "4×12/12", "Orqa oyoq ko'tarilgan, chuqur lunge."),
            ("Jump Squat", "4×15", "Portlovchi yuqoriga, yumshoq qo'nish."),
            ("Single-leg Calf Raise", "4×25/25", "To'liq kenglik, sekin tushish."),
            ("High Knees", "1×10d", "Tizzalarni yuqoriga. Tez sur'at, 10 daqiqa."),
        ],
    ),
    (
        "Sh — Qo'llar (Triceps + Biceps)",
        "Qo'llar — Triceps + Biceps. Tezlik emas, sifat muhim.",
        "tip:arms",
        [
            ("Diamond Push-up", "5×10", "Bosh barmoq va ko'rsatkich tegib tursin."),
            ("Bench Dip", "4×15", "Qo'llar orqadagi stulda, 90° gacha tushing."),
            ("Close-grip Push-up", "4×12", "Qo'llar ko'krak ostida, tirsak tanaga yaqin."),
            ("Bicep Curl", "4×15", "Suv shishasi. To'liq kenglik, tepada siqish."),
            ("Hammer Curl", "4×12", "Neytral ushlab tutish, almashinib."),
        ],
    ),
    (
        "Ya — Faol dam + Cho'zilish",
        "Yakshanba — faol dam. 8-9 soat uxlash. Mushaklar dam olishda o'sadi.",
        "tip:rest",
        [
            ("30 min Yurish", "1×30d", "Yengil sur'at. Faol dam olish."),
            ("Chest Opener Stretch", "3×45s", "Qo'llar orqada, ko'krak oldinga. 45 sek."),
            ("Shoulder Stretch", "3×45s", "Qo'lni tana bo'ylab tortish."),
            ("Stomach Vacuum", "3×40s", "Ixtiyoriy. Ertalabki vacuum."),
        ],
    ),
]

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def import_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📥 Otabek hafta rejasini import qilish",
                    callback_data="seed:otabek:ask",
                )
            ],
            [InlineKeyboardButton(text="◀️ Mashqlar", callback_data="menu:workouts")],
        ]
    )


def import_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, import qilish", callback_data="seed:otabek:go"),
                InlineKeyboardButton(text="❌ Bekor", callback_data="menu:workouts"),
            ]
        ]
    )


def import_time_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏭ Bu kunni o'tkazish", callback_data="seed:t:skip"),
            ],
            [
                InlineKeyboardButton(text="⛔ Hammasini to'xtatish", callback_data="seed:t:stop"),
            ],
        ]
    )


@router.callback_query(F.data == "wo:import")
async def cb_import_menu(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await msg.edit_text(
        "<b>📥 Tayyor reja import</b>\n\n"
        "Otabek — Life OS 2026 dan 7 kunlik reja (33 ta mashq) bir bosishda qo'shiladi.",
        reply_markup=import_menu(),
    )
    await cb.answer()


@router.callback_query(F.data == "seed:otabek:ask")
async def cb_seed_ask(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    lines = ["<b>📥 Otabek hafta rejasi</b>", ""]
    total_ex = 0
    for name, _, _, exs in OTABEK_PLAN:
        lines.append(f"• <b>{escape(name)}</b> — {len(exs)} ta mashq")
        total_ex += len(exs)
    lines.append("")
    lines.append(f"Jami: <b>{len(OTABEK_PLAN)}</b> kun · <b>{total_ex}</b> mashq")
    lines.append("")
    lines.append(
        "Import-dan keyin har kunga vaqt (HH:MM) kiritasiz — bot o'sha kun "
        'uchun jadval ulaydi. Vaqt berishni xohlamasangiz "⏭ O\'tkazish".'
    )
    await msg.edit_text("\n".join(lines), reply_markup=import_confirm())
    await cb.answer()


async def _prompt_next_time(msg: Message, state: FSMContext) -> None:
    """FSM data dan keyingi pending kunni olib HH:MM so'raydi."""
    data = await state.get_data()
    pending: list[list[int | str]] = data.get("pending", [])
    done: int = data.get("done", 0)
    skipped: int = data.get("skipped", 0)
    total: int = data.get("total", 0)
    if not pending:
        # Wizard tugadi
        await state.clear()
        text = [
            "<b>✅ Import yakunlandi</b>",
            "",
            f"➕ Yangi kun: <b>{total}</b>",
            f"📅 Jadval ulandi: <b>{done}</b>",
        ]
        if skipped:
            text.append(f"⏭ Vaqtsiz qoldirilgan: <b>{skipped}</b>")
        text.append("")
        text.append("Keyin xohlasangiz 💪 Mashqlar → kun → 📅 Jadval orqali qo'shasiz.")
        await msg.answer(
            "\n".join(text),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀️ Mashqlar", callback_data="menu:workouts")]]
            ),
        )
        return
    workout_id, day_idx, name = pending[0]
    progress = done + skipped + 1
    prompt = (
        f"<b>⏰ Vaqt kiritish ({progress}/{total})</b>\n\n"
        f"<b>{escape(str(name))}</b>\n"
        f"Kun: <b>{DOW_NAMES_UZ[int(day_idx)]}</b>\n\n"
        "HH:MM formatida vaqt yuboring (masalan: <code>07:00</code> yoki <code>19:30</code>).\n"
        "Vaqt kerak bo'lmasa pastdagi tugmani bosing."
    )
    await msg.answer(prompt, reply_markup=import_time_actions())


@router.callback_query(F.data == "seed:otabek:go")
async def cb_seed_go(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    owner_id = cb.from_user.id if cb.from_user else 0
    created: list[list[int | str]] = []  # [[workout_id, day_idx, name], ...]
    skipped_workouts = 0
    created_exs = 0
    async with AsyncSessionLocal() as session:
        existing = {w.name for w in await list_workouts(session)}
        for day_idx, (name, desc, _, exs) in enumerate(OTABEK_PLAN):
            if name in existing:
                skipped_workouts += 1
                continue
            workout = await add_workout(session, name=name, description=desc, created_by=owner_id)
            created.append([workout.id, day_idx, name])
            for idx, (ex_name, spec, ex_desc) in enumerate(exs):
                await add_exercise(
                    session,
                    workout_id=workout.id,
                    name=ex_name,
                    spec=spec,
                    description=ex_desc,
                    order_idx=idx,
                )
                created_exs += 1
        await session.commit()

    intro = [
        "<b>✅ Mashqlar qo'shildi</b>",
        "",
        f"➕ Yangi kun: <b>{len(created)}</b>",
        f"➕ Yangi mashq: <b>{created_exs}</b>",
    ]
    if skipped_workouts:
        intro.append(f"⏭ O'tkazilgan kun (mavjud edi): <b>{skipped_workouts}</b>")
    intro.append("")
    if created:
        intro.append("Endi har kun uchun vaqt (HH:MM) kiritasiz — bot eslatib turadi.")
    else:
        intro.append("Hech qanday yangi kun qo'shilmadi (hammasi mavjud).")
    await msg.edit_text(
        "\n".join(intro),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Mashqlar", callback_data="menu:workouts")]]
        ),
    )

    if not created:
        await cb.answer("Import yakunlandi")
        return

    await state.set_state(ImportTimesStates.waiting_for_time)
    await state.set_data(
        {
            "pending": created,
            "done": 0,
            "skipped": 0,
            "total": len(created),
        }
    )
    await _prompt_next_time(msg, state)
    await cb.answer("Vaqt kiriting")


@router.message(ImportTimesStates.waiting_for_time)
async def m_import_time(message: Message, state: FSMContext, scheduler: WorkoutScheduler) -> None:
    if not is_owner_message(message):
        return
    raw = (message.text or "").strip()
    m = TIME_RE.match(raw)
    if not m:
        await message.answer(
            "❌ Vaqt format xato. <code>HH:MM</code> ko'rinishida yuboring " "(masalan: <code>07:00</code>).",
            reply_markup=import_time_actions(),
        )
        return
    hour = int(m.group(1))
    minute = int(m.group(2))
    data = await state.get_data()
    pending: list[list[int | str]] = list(data.get("pending", []))
    if not pending:
        await state.clear()
        return
    workout_id_raw, day_idx_raw, _name = pending[0]
    workout_id = int(workout_id_raw)
    day_idx = int(day_idx_raw)
    days_mask = 1 << day_idx
    timeout = settings.WORKOUT_ACK_TIMEOUT_MIN
    async with AsyncSessionLocal() as session:
        sch = await add_workout_schedule(
            session,
            workout_id=workout_id,
            days_mask=days_mask,
            hour=hour,
            minute=minute,
            ack_timeout_min=timeout,
        )
        await session.commit()
        scheduler.add_schedule(sch)
    await state.update_data(
        pending=pending[1:],
        done=int(data.get("done", 0)) + 1,
        skipped=int(data.get("skipped", 0)),
        total=int(data.get("total", 0)),
    )
    await message.answer(f"✅ {DOW_NAMES_UZ[day_idx]} {hour:02d}:{minute:02d} ulandi.")
    await _prompt_next_time(message, state)


@router.callback_query(ImportTimesStates.waiting_for_time, F.data == "seed:t:skip")
async def cb_import_skip(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    data = await state.get_data()
    pending: list[list[int | str]] = list(data.get("pending", []))
    if not pending:
        await state.clear()
        await cb.answer()
        return
    await state.update_data(
        pending=pending[1:],
        done=int(data.get("done", 0)),
        skipped=int(data.get("skipped", 0)) + 1,
        total=int(data.get("total", 0)),
    )
    await cb.answer("O'tkazildi")
    await _prompt_next_time(msg, state)


@router.callback_query(ImportTimesStates.waiting_for_time, F.data == "seed:t:stop")
async def cb_import_stop(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    data = await state.get_data()
    pending: list[list[int | str]] = list(data.get("pending", []))
    skipped_now = len(pending)
    await state.clear()
    text = [
        "<b>⛔ Vaqt kiritish to'xtatildi</b>",
        "",
        f"📅 Jadval ulandi: <b>{int(data.get('done', 0))}</b>",
        f"⏭ Vaqtsiz qolgan: <b>{int(data.get('skipped', 0)) + skipped_now}</b>",
        "",
        "Keyin xohlasangiz 💪 Mashqlar → kun → 📅 Jadval orqali qo'shasiz.",
    ]
    await msg.answer(
        "\n".join(text),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Mashqlar", callback_data="menu:workouts")]]
        ),
    )
    await cb.answer("To'xtatildi")


__all__ = ["router", "OTABEK_PLAN"]
