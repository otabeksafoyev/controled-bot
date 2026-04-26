"""Main menu + status/help/forwarded handlers (buttons)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from telethon import TelegramClient

from bot.common import accessible, is_owner_callback, is_owner_message
from bot.keyboards import back_to_main, main_menu
from config import settings
from db.engine import AsyncSessionLocal
from db.queries import count_pending, list_channels, recent_forwarded
from kaworai.queries import get_animes

log = logging.getLogger(__name__)
router = Router(name="menu")
router.message.filter(F.chat.type == "private")


HELP_TEXT = (
    "<b>Kaworai Watcher</b>\n\n"
    "Obuna bo'lgan kanallaringizda yangi video kelganda:\n"
    "• Caption-dan qism raqami olinadi (<code>5-qism</code>, <code>Qism 5</code>, va h.k.)\n"
    "• Caption ichidan kaworai DB-dagi anime nomi avtomatik qidiriladi\n"
    "• Topilsa — kaworai SECRET_CHANNEL-ga <code>ID: X\\nQism: Y</code> bilan yuboriladi\n"
    "• Topilmasa — sizga inline tugmali xabar kelib, qo'lda biriktirishingiz mumkin\n\n"
    "Shuningdek, kontaktlaringizdan kelgan shaxsiy xabarlarga avtojavob qo'shish mumkin.\n\n"
    "Boshlash: 📺 Kanallar → ➕ Kanal qo'shish."
)


async def _show_main(message_or_cb: Message | CallbackQuery) -> None:
    async with AsyncSessionLocal() as session:
        pending_cnt = await count_pending(session)
    text = "<b>Bosh menyu</b>\nTanlang:"
    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=main_menu(pending_cnt))
    else:
        msg = accessible(message_or_cb)
        if msg is None:
            return
        await msg.edit_text(text, reply_markup=main_menu(pending_cnt))
        await message_or_cb.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    await state.clear()
    async with AsyncSessionLocal() as session:
        pending_cnt = await count_pending(session)
    await message.answer(HELP_TEXT, reply_markup=main_menu(pending_cnt))


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    await state.clear()
    await _show_main(message)


@router.callback_query(F.data == "menu:main")
async def cb_main(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    await state.clear()
    await _show_main(cb)


@router.callback_query(F.data == "menu:help")
async def cb_help(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await msg.edit_text(HELP_TEXT, reply_markup=back_to_main())
    await cb.answer()


@router.callback_query(F.data == "menu:status")
async def cb_status(cb: CallbackQuery, userbot: TelegramClient) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    try:
        me = await userbot.get_me()
        user_line = f"Userbot: @{me.username or me.first_name} (id=<code>{me.id}</code>)"
    except Exception as exc:
        user_line = f"Userbot: <b>XATO</b> — {exc}"

    async with AsyncSessionLocal() as session:
        channels = await list_channels(session)
        pending_cnt = await count_pending(session)
        recent = await recent_forwarded(session, limit=5)

    kaworai_line = "Kaworai DB: <b>o'chirilgan</b> (KAWORAI_DATABASE_URL yo'q)"
    if settings.KAWORAI_DATABASE_URL:
        animes = await get_animes()
        kaworai_line = (
            f"Kaworai DB: <b>{len(animes)}</b> anime"
            if animes
            else "Kaworai DB: <b>ulanish muvaffaqiyatsiz</b>"
        )

    text = (
        f"{user_line}\n"
        f"Kuzatilayotgan kanallar: <b>{len(channels)}</b>\n"
        f"Kutilayotgan video: <b>{pending_cnt}</b>\n"
        f"{kaworai_line}\n"
        f"SECRET_CHANNEL: <code>{settings.SECRET_CHANNEL_ID}</code>\n"
        f"So'nggi yuborilgan: <b>{len(recent)}</b>"
    )
    await msg.edit_text(text, reply_markup=back_to_main())
    await cb.answer()


@router.callback_query(F.data == "menu:forwarded")
async def cb_forwarded(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    async with AsyncSessionLocal() as session:
        rows = await recent_forwarded(session, limit=20)
    if not rows:
        text = "Hali hech narsa yuborilmagan."
    else:
        lines = [
            f"#{r.id} anime={r.anime_id} ep={r.episode} kanal=<code>{r.source_channel_id}</code>"
            for r in rows
        ]
        text = "<b>So'nggi yuborilganlar</b>\n" + "\n".join(lines)
    await msg.edit_text(text, reply_markup=back_to_main())
    await cb.answer()


@router.callback_query(F.data == "wiz:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    await state.clear()
    msg = accessible(cb)
    if msg is not None:
        await msg.edit_text("Bekor qilindi.", reply_markup=back_to_main())
    await cb.answer("Bekor qilindi")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    await state.clear()
    async with AsyncSessionLocal() as session:
        pending_cnt = await count_pending(session)
    await message.answer("Bekor qilindi.", reply_markup=main_menu(pending_cnt))
