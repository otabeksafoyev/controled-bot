"""Auto-reply management — buttons."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.common import accessible, is_owner_callback, is_owner_message
from bot.keyboards import (
    back_to_main,
    confirm_delete_reply,
    pattern_type_choice,
    replies_list,
    reply_detail,
    wizard_cancel,
)
from bot.states import AddReplyStates
from db.engine import AsyncSessionLocal
from db.models import PATTERN_REGEX, PATTERN_SUBSTRING
from db.queries import (
    add_auto_reply,
    get_auto_reply,
    list_auto_replies,
    remove_auto_reply,
    toggle_auto_reply,
)
from userbot.rules import validate_regex

log = logging.getLogger(__name__)
router = Router(name="replies")
router.message.filter(F.chat.type == "private")


async def _render_list(cb: CallbackQuery) -> None:
    msg = accessible(cb)
    if msg is None:
        return
    async with AsyncSessionLocal() as session:
        replies = await list_auto_replies(session)
    if not replies:
        text = (
            "<b>Avtojavoblar</b>\n\n"
            "Hozir avtojavob qoidalari yo'q.\n"
            "Yangi qo'shish uchun quyidagi tugmani bosing.\n\n"
            "ℹ️ Avtojavoblar <b>faqat kontaktlaringizdan</b> kelgan shaxsiy xabarlarga yuboriladi."
        )
    else:
        text = "<b>Avtojavoblar</b>\n\n" "🟢 = yoqilgan, ⚪ = o'chirilgan. Qoidani bosib o'zgartiring."
    await msg.edit_text(text, reply_markup=replies_list(replies))
    await cb.answer()


@router.callback_query(F.data == "menu:replies")
async def cb_replies(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    await state.clear()
    await _render_list(cb)


@router.callback_query(F.data.startswith("ar:view:"))
async def cb_ar_view(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    msg = accessible(cb)
    if msg is None:
        return
    reply_id = int(cb.data.split(":", 2)[2])
    async with AsyncSessionLocal() as session:
        reply = await get_auto_reply(session, reply_id)
    if reply is None:
        await cb.answer("Topilmadi", show_alert=True)
        return
    pat = reply.pattern if reply.pattern else "«har qanday matn»"
    state_lbl = "🟢 yoqilgan" if reply.active else "⚪ o'chirilgan"
    ptype_lbl = "regex" if reply.pattern_type == PATTERN_REGEX else "matn"
    await msg.edit_text(
        f"<b>Avtojavob #{reply.id}</b>\n"
        f"Holati: {state_lbl}\n"
        f"Pattern [<i>{ptype_lbl}</i>]: <code>{pat}</code>\n\n"
        f"<b>Javob:</b>\n{reply.reply_text}",
        reply_markup=reply_detail(reply),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ar:toggle:"))
async def cb_ar_toggle(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    reply_id = int(cb.data.split(":", 2)[2])
    async with AsyncSessionLocal() as session:
        row = await toggle_auto_reply(session, reply_id=reply_id)
        await session.commit()
    if row is None:
        await cb.answer("Topilmadi", show_alert=True)
        return
    await cb.answer("Holati o'zgardi")
    # re-render the detail view
    cb.data = f"ar:view:{reply_id}"
    await cb_ar_view(cb)


@router.callback_query(F.data.startswith("ar:delask:"))
async def cb_ar_delask(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    msg = accessible(cb)
    if msg is None:
        return
    reply_id = int(cb.data.split(":", 2)[2])
    await msg.edit_text(
        f"Avtojavob #<b>{reply_id}</b> ni o'chirishni tasdiqlaysizmi?",
        reply_markup=confirm_delete_reply(reply_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ar:delok:"))
async def cb_ar_delok(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    reply_id = int(cb.data.split(":", 2)[2])
    async with AsyncSessionLocal() as session:
        await remove_auto_reply(session, reply_id=reply_id)
        await session.commit()
    await cb.answer("O'chirildi")
    await _render_list(cb)


# -------- Add auto-reply wizard --------


@router.callback_query(F.data == "ar:add")
async def cb_ar_add(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await state.set_state(AddReplyStates.waiting_for_pattern_type)
    await msg.edit_text(
        "<b>Yangi avtojavob</b>\n\nQoida turini tanlang:",
        reply_markup=pattern_type_choice("reply"),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ptype:reply:"))
async def cb_reply_ptype(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    msg = accessible(cb)
    if msg is None:
        return
    kind = cb.data.split(":", 2)[2]
    if kind == "all":
        await state.update_data(pattern="", pattern_type=PATTERN_SUBSTRING)
        await state.set_state(AddReplyStates.waiting_for_reply_text)
        await msg.edit_text(
            "Qoida: <b>har qanday matn</b>ga javob.\n\nEndi javob matnini yuboring:",
            reply_markup=wizard_cancel(),
        )
        await cb.answer()
        return
    pattern_type = PATTERN_REGEX if kind == "regex" else PATTERN_SUBSTRING
    await state.update_data(pattern_type=pattern_type)
    await state.set_state(AddReplyStates.waiting_for_pattern)
    hint = (
        "Masalan: <code>salom</code> — xabar matnida shu so'z bo'lsa mos keladi."
        if pattern_type == PATTERN_SUBSTRING
        else "Masalan: <code>(?i)^salom|hi\\b</code>. Python regex."
    )
    await msg.edit_text(
        f"<b>Kalit so'z</b> yuboring:\n{hint}",
        reply_markup=wizard_cancel(),
    )
    await cb.answer()


@router.message(AddReplyStates.waiting_for_pattern)
async def on_reply_pattern(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message) or not message.text:
        return
    pattern = message.text.strip()
    data = await state.get_data()
    pattern_type = data.get("pattern_type", PATTERN_SUBSTRING)
    if pattern_type == PATTERN_REGEX:
        err = validate_regex(pattern)
        if err is not None:
            await message.answer(
                f"Regex xato: <code>{err}</code>\nQaytadan yuboring.",
                reply_markup=wizard_cancel(),
            )
            return
    await state.update_data(pattern=pattern)
    await state.set_state(AddReplyStates.waiting_for_reply_text)
    await message.answer(
        f"Pattern saqlandi: <code>{pattern}</code>\n\n<b>Javob matnini</b> yuboring:",
        reply_markup=wizard_cancel(),
    )


@router.message(AddReplyStates.waiting_for_reply_text)
async def on_reply_text(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message) or not message.text:
        return
    reply_text = message.text
    data = await state.get_data()
    pattern = data.get("pattern", "")
    pattern_type = data.get("pattern_type", PATTERN_SUBSTRING)
    async with AsyncSessionLocal() as session:
        await add_auto_reply(
            session,
            pattern=pattern,
            pattern_type=pattern_type,
            reply_text=reply_text,
            created_by=message.from_user.id if message.from_user else 0,
        )
        await session.commit()
    await state.clear()
    pat_display = pattern if pattern else "«har qanday matn»"
    await message.answer(
        f"✅ Avtojavob qo'shildi:\n"
        f"Pattern: <code>{pat_display}</code> ({pattern_type})\n"
        f"Javob: {reply_text}",
        reply_markup=back_to_main(),
    )
