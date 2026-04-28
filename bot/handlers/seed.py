"""Tayyor mashq rejalarini import qilish handlerlari.

'Otabek — Life OS 2026' rejasidan 7 kunlik mashqlar (33 ta element) bir tugma
bilan DB-ga import qilinadi. Har kun uchun bitta Workout yaratiladi va u
o'sha kun (single-day mask) jadvaliga ulanishi mumkin.
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.common import accessible, is_owner_callback
from db.engine import AsyncSessionLocal
from db.queries import add_exercise, add_workout, list_workouts

log = logging.getLogger(__name__)
router = Router(name="seed")

# 7-day plan from Otabek Life OS 2026: each day = (workout_name, description,
# tip, exercises[]). spec column packed with set/rep/format hints used by the
# reminder line formatter.
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
        "<i>Eslatma:</i> takror import bo'lmaydi — bir xil nomli kun mashqi mavjud bo'lsa, "
        "qaytadan qo'shilmaydi."
    )
    await msg.edit_text("\n".join(lines), reply_markup=import_confirm())
    await cb.answer()


@router.callback_query(F.data == "seed:otabek:go")
async def cb_seed_go(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    owner_id = cb.from_user.id if cb.from_user else 0
    created_workouts = 0
    skipped_workouts = 0
    created_exs = 0
    async with AsyncSessionLocal() as session:
        existing = {w.name for w in await list_workouts(session)}
        for name, desc, _, exs in OTABEK_PLAN:
            if name in existing:
                skipped_workouts += 1
                continue
            workout = await add_workout(session, name=name, description=desc, created_by=owner_id)
            created_workouts += 1
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

    text = [
        "<b>✅ Import yakunlandi</b>",
        "",
        f"➕ Yangi kun: <b>{created_workouts}</b>",
        f"➕ Yangi mashq: <b>{created_exs}</b>",
    ]
    if skipped_workouts:
        text.append(f"⏭ O'tkazilgan (mavjud): <b>{skipped_workouts}</b>")
    text.append("")
    text.append(
        "Endi 💪 Mashqlar yoki 📆 Hafta rejasi orqali kun ustiga bosib, "
        "har biriga jadval (HH:MM) va media qo'shing."
    )
    await msg.edit_text(
        "\n".join(text),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="◀️ Mashqlar", callback_data="menu:workouts")]]
        ),
    )
    await cb.answer("Import yakunlandi")


__all__ = ["router", "OTABEK_PLAN"]
