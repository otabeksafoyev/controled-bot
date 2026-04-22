"""Main menu + status/help/forwarded handlers (buttons)."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from telethon import TelegramClient

from bot.common import accessible, is_owner_callback, is_owner_message
from bot.keyboards import back_to_main, main_menu
from config import settings
from db.engine import AsyncSessionLocal
from db.queries import list_all_rules, recent_forwarded

log = logging.getLogger(__name__)
router = Router(name="menu")
router.message.filter(F.chat.type == "private")


HELP_TEXT = (
    "<b>Kaworai Watcher</b>\n\n"
    "Men obuna bo'lgan kanallaringizni kuzataman. Har kanal uchun bir yoki bir nechta "
    "<b>qoida</b> qo'shishingiz mumkin: kalit so'z (yoki regex) + anime ID. "
    "Yangi video caption-iga qoida mos kelsa — u kaworai SECRET_CHANNEL-ga qism qilib "
    "avtomatik yuboriladi.\n\n"
    "Shuningdek, <b>kontakt</b>laringizdan kelgan shaxsiy xabarlarga avtojavob qo'shishingiz mumkin.\n\n"
    "Boshlash: 📺 Kanallar → ➕ Yangi kanal qo'shish."
)


async def _show_main(message_or_cb: Message | CallbackQuery) -> None:
    text = "<b>Bosh menyu</b>\nTanlang:"
    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=main_menu())
    else:
        msg = accessible(message_or_cb)
        if msg is None:
            return
        await msg.edit_text(text, reply_markup=main_menu())
        await message_or_cb.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    await state.clear()
    await message.answer(HELP_TEXT, reply_markup=main_menu())


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
        rules = await list_all_rules(session)
        recent = await recent_forwarded(session, limit=5)
    channels_count = len({r.channel_id for r in rules})
    text = (
        f"{user_line}\n"
        f"Kuzatilayotgan kanallar: <b>{channels_count}</b>\n"
        f"Qoidalar: <b>{len(rules)}</b>\n"
        f"SECRET_CHANNEL: <code>{settings.SECRET_CHANNEL_ID}</code>\n"
        f"So'nggi 5 yuborilgan: <b>{len(recent)}</b>"
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
            f"#{r.id} anime={r.anime_id} ep={r.episode} " f"kanal=<code>{r.source_channel_id}</code>"
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
    await message.answer("Bekor qilindi.", reply_markup=main_menu())


# Legacy text commands that still work
@router.message(Command("status"))
async def cmd_status(message: Message, userbot: TelegramClient, command: Any) -> None:
    if not is_owner_message(message):
        return
    try:
        me = await userbot.get_me()
        user_line = f"Userbot: @{me.username or me.first_name} (id={me.id})"
    except Exception as exc:
        user_line = f"Userbot: XATO — {exc}"
    async with AsyncSessionLocal() as session:
        rules = await list_all_rules(session)
        recent = await recent_forwarded(session, limit=5)
    channels_count = len({r.channel_id for r in rules})
    await message.answer(
        f"{user_line}\n"
        f"Kanallar: {channels_count}\n"
        f"Qoidalar: {len(rules)}\n"
        f"SECRET_CHANNEL: <code>{settings.SECRET_CHANNEL_ID}</code>\n"
        f"So'nggi yuborilgan: {len(recent)}"
    )


@router.message(Command("forwarded"))
async def cmd_forwarded(message: Message) -> None:
    if not is_owner_message(message):
        return
    async with AsyncSessionLocal() as session:
        rows = await recent_forwarded(session, limit=20)
    if not rows:
        await message.answer("Hali hech narsa yuborilmagan.")
        return
    lines = [
        f"#{row.id} anime={row.anime_id} ep={row.episode} uid=<code>{row.file_unique_id}</code>"
        for row in rows
    ]
    await message.answer("\n".join(lines))
