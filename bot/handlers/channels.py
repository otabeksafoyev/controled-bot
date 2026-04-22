"""Channel subscribe / rule management — both buttons and legacy text commands."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from bot.common import (
    accessible,
    channel_id_to_db,
    get_channel_title,
    is_owner_callback,
    is_owner_message,
    resolve_channel,
)
from bot.keyboards import (
    back_to_main,
    channel_detail,
    channels_list,
    confirm_delete,
    confirm_leave,
    pattern_type_choice,
    wizard_cancel,
)
from bot.states import AddChannelStates, AddRuleStates
from db.engine import AsyncSessionLocal
from db.models import PATTERN_REGEX, PATTERN_SUBSTRING
from db.queries import (
    add_rule,
    get_rule,
    get_rules_for_channel,
    list_all_rules,
    remove_rule,
    remove_rules_for_channel,
)
from userbot.rules import validate_regex

log = logging.getLogger(__name__)
router = Router(name="channels")
router.message.filter(F.chat.type == "private")


# ---------------- List + view ----------------


async def _render_channels_list(message_or_cb: Message | CallbackQuery, userbot: TelegramClient) -> None:
    async with AsyncSessionLocal() as session:
        rules = await list_all_rules(session)
    counts: dict[int, int] = {}
    for r in rules:
        counts[r.channel_id] = counts.get(r.channel_id, 0) + 1
    groups: list[tuple[int, int, str | None]] = []
    for cid, count in counts.items():
        title = await get_channel_title(userbot, cid)
        groups.append((cid, count, title))
    groups.sort(key=lambda x: (x[2] or "").lower())

    text = "<b>Kanallar</b>\n\n" + (
        "Hozir kuzatilayotgan kanal yo'q.\n\n" "Quyidagi tugma orqali kanal qo'shing."
        if not groups
        else "Kanalni bosib tegishli qoidalarini ko'ring yoki yangisini qo'shing:"
    )
    kb = channels_list(groups)
    if isinstance(message_or_cb, Message):
        await message_or_cb.answer(text, reply_markup=kb)
    else:
        msg = accessible(message_or_cb)
        if msg is None:
            return
        await msg.edit_text(text, reply_markup=kb)
        await message_or_cb.answer()


@router.callback_query(F.data == "menu:channels")
async def cb_channels(cb: CallbackQuery, userbot: TelegramClient, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    await state.clear()
    await _render_channels_list(cb, userbot)


async def _render_channel_detail(cb: CallbackQuery, userbot: TelegramClient, channel_id: int) -> None:
    msg = accessible(cb)
    if msg is None:
        return
    async with AsyncSessionLocal() as session:
        rules = await get_rules_for_channel(session, channel_id)
    title = await get_channel_title(userbot, channel_id)
    lines = [
        f"<b>{title or channel_id}</b>",
        f"ID: <code>{channel_id}</code>",
        f"Qoidalar soni: <b>{len(rules)}</b>",
        "",
    ]
    if rules:
        for r in rules:
            pat = r.pattern if r.pattern else "«istalgan»"
            ptype = "regex" if r.pattern_type == PATTERN_REGEX else "matn"
            lines.append(f"• #{r.id} [<i>{ptype}</i>] <code>{pat}</code> → anime <b>#{r.anime_id}</b>")
    else:
        lines.append("Qoida yo'q. Qo'shish uchun quyidagi tugmani bosing.")
    await msg.edit_text("\n".join(lines), reply_markup=channel_detail(channel_id, rules))
    await cb.answer()


@router.callback_query(F.data.startswith("ch:view:"))
async def cb_view_channel(cb: CallbackQuery, userbot: TelegramClient, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    await state.clear()
    channel_id = int(cb.data.split(":", 2)[2])
    await _render_channel_detail(cb, userbot, channel_id)


# ---------------- Subscribe wizard ----------------


@router.callback_query(F.data == "ch:add")
async def cb_add_channel(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        return
    msg = accessible(cb)
    if msg is None:
        return
    await state.set_state(AddChannelStates.waiting_for_channel)
    await msg.edit_text(
        "<b>Kanal qo'shish</b>\n\n"
        "Kanal @username yoki invite linkini yuboring.\n"
        "Misol: <code>@myanime_uz</code> yoki <code>https://t.me/+AbC123</code>",
        reply_markup=wizard_cancel(),
    )
    await cb.answer()


@router.message(AddChannelStates.waiting_for_channel)
async def on_add_channel_input(message: Message, state: FSMContext, userbot: TelegramClient) -> None:
    if not is_owner_message(message) or not message.text:
        return
    arg = message.text.strip()
    try:
        if "t.me/+" in arg or "/joinchat/" in arg:
            hash_part = arg.rsplit("+", 1)[-1] if "t.me/+" in arg else arg.rsplit("/", 1)[-1]
            with contextlib.suppress(UserAlreadyParticipantError):
                await userbot(ImportChatInviteRequest(hash_part))
            await message.answer(
                "Obuna bo'lindi (invite link orqali).\n"
                "Kanallarni <b>📺 Kanallar</b> menyusidan ko'rishingiz mumkin, "
                "ammo qoida qo'shish uchun avval kanal captioni yoki xabari kelib qoladi "
                "va keyin kanal ro'yxatiga qo'shiladi.",
                reply_markup=back_to_main(),
            )
            await state.clear()
            return
        entity = await userbot.get_entity(arg)
        await userbot(JoinChannelRequest(entity))
        ch_id = channel_id_to_db(entity.id)
        title = getattr(entity, "title", arg)
        await message.answer(
            f"Obuna: <b>{title}</b>\nID: <code>{ch_id}</code>\n\n"
            "Endi qoida qo'shing — bo'sh qoldirsangiz kanaldagi barcha videolar "
            "tanlangan anime-ga qism qilib yuboriladi.",
            reply_markup=wizard_cancel(),
        )
        await state.set_state(AddRuleStates.waiting_for_pattern_type)
        await state.update_data(channel_id=ch_id)
        await message.answer(
            "<b>Qoida turi</b>ni tanlang:",
            reply_markup=pattern_type_choice("rule"),
        )
    except (InviteHashExpiredError, InviteHashInvalidError):
        await message.answer("Invite link yaroqsiz yoki muddati tugagan.")
    except ChannelPrivateError:
        await message.answer("Kanal yopiq — invite link kerak.")
    except FloodWaitError as exc:
        await message.answer(f"Telegram rate limit: {exc.seconds}s kutish kerak.")
    except Exception as exc:
        log.exception("subscribe xato")
        await message.answer(f"Xato: {exc}")


# ---------------- Add rule wizard ----------------


@router.callback_query(F.data.startswith("ch:addrule:"))
async def cb_add_rule(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    msg = accessible(cb)
    if msg is None:
        return
    channel_id = int(cb.data.split(":", 2)[2])
    await state.set_state(AddRuleStates.waiting_for_pattern_type)
    await state.update_data(channel_id=channel_id)
    await msg.edit_text(
        "<b>Yangi qoida</b>\n\nQoida turini tanlang:",
        reply_markup=pattern_type_choice("rule"),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ptype:rule:"))
async def cb_rule_ptype(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    msg = accessible(cb)
    if msg is None:
        return
    kind = cb.data.split(":", 2)[2]  # substring | regex | all
    if kind == "all":
        await state.update_data(pattern="", pattern_type=PATTERN_SUBSTRING)
        await state.set_state(AddRuleStates.waiting_for_anime_id)
        await msg.edit_text(
            "Qoida: <b>barcha videolar</b> shu kanaldan.\n\n"
            "Endi <b>anime ID</b> ni yuboring (butun son, masalan <code>15</code>):",
            reply_markup=wizard_cancel(),
        )
        await cb.answer()
        return
    pattern_type = PATTERN_REGEX if kind == "regex" else PATTERN_SUBSTRING
    await state.update_data(pattern_type=pattern_type)
    await state.set_state(AddRuleStates.waiting_for_pattern)
    hint = (
        "Masalan: <code>Naruto</code> — caption ichida shu so'z uchrasa mos keladi (registr muhim emas)."
        if pattern_type == PATTERN_SUBSTRING
        else "Masalan: <code>(?i)naruto\\s*shippuden</code>. Python regex."
    )
    await msg.edit_text(
        f"<b>Kalit so'z</b> yuboring:\n{hint}",
        reply_markup=wizard_cancel(),
    )
    await cb.answer()


@router.message(AddRuleStates.waiting_for_pattern)
async def on_rule_pattern(message: Message, state: FSMContext) -> None:
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
    await state.set_state(AddRuleStates.waiting_for_anime_id)
    await message.answer(
        f"Pattern saqlandi: <code>{pattern}</code>\n\n" "Endi <b>anime ID</b> ni yuboring (butun son):",
        reply_markup=wizard_cancel(),
    )


@router.message(AddRuleStates.waiting_for_anime_id)
async def on_rule_anime_id(message: Message, state: FSMContext, userbot: TelegramClient) -> None:
    if not is_owner_message(message) or not message.text:
        return
    try:
        anime_id = int(message.text.strip())
    except ValueError:
        await message.answer("Anime ID butun son bo'lishi kerak. Qayta yuboring.")
        return
    data = await state.get_data()
    channel_id = data.get("channel_id")
    pattern = data.get("pattern", "")
    pattern_type = data.get("pattern_type", PATTERN_SUBSTRING)
    if channel_id is None:
        await message.answer("Ichki xato: channel_id yo'q. Qaytadan urinib ko'ring.")
        await state.clear()
        return
    async with AsyncSessionLocal() as session:
        await add_rule(
            session,
            channel_id=int(channel_id),
            pattern=pattern,
            pattern_type=pattern_type,
            anime_id=anime_id,
            created_by=message.from_user.id if message.from_user else 0,
        )
        await session.commit()
    await state.clear()
    title = await get_channel_title(userbot, int(channel_id))
    pat_display = pattern if pattern else "«istalgan»"
    await message.answer(
        f"✅ Qoida qo'shildi:\n"
        f"Kanal: <b>{title or channel_id}</b>\n"
        f"Pattern: <code>{pat_display}</code> ({pattern_type})\n"
        f"Anime: <b>#{anime_id}</b>",
        reply_markup=back_to_main(),
    )


# ---------------- Delete rule ----------------


@router.callback_query(F.data.startswith("rule:delask:"))
async def cb_rule_delask(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    msg = accessible(cb)
    if msg is None:
        return
    rule_id = int(cb.data.split(":", 2)[2])
    async with AsyncSessionLocal() as session:
        rule = await get_rule(session, rule_id)
    if rule is None:
        await cb.answer("Qoida topilmadi", show_alert=True)
        return
    pat = rule.pattern if rule.pattern else "«istalgan»"
    await msg.edit_text(
        f"Qoida <b>#{rule.id}</b> ni o'chirishni tasdiqlaysizmi?\n"
        f"Kanal: <code>{rule.channel_id}</code>\n"
        f"Pattern: <code>{pat}</code>\n"
        f"Anime: #{rule.anime_id}",
        reply_markup=confirm_delete(rule.id, rule.channel_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("rule:delok:"))
async def cb_rule_delok(cb: CallbackQuery, userbot: TelegramClient) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    rule_id = int(cb.data.split(":", 2)[2])
    async with AsyncSessionLocal() as session:
        rule = await get_rule(session, rule_id)
        if rule is None:
            await cb.answer("Allaqachon o'chirilgan", show_alert=True)
            return
        channel_id = rule.channel_id
        await remove_rule(session, rule_id=rule_id)
        await session.commit()
    await cb.answer("O'chirildi")
    await _render_channel_detail(cb, userbot, channel_id)


# ---------------- Leave channel ----------------


@router.callback_query(F.data.startswith("ch:leave:"))
async def cb_leave_ask(cb: CallbackQuery) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    msg = accessible(cb)
    if msg is None:
        return
    channel_id = int(cb.data.split(":", 2)[2])
    await msg.edit_text(
        f"Kanaldan chiqishni tasdiqlaysizmi?\nID: <code>{channel_id}</code>\n\n"
        "Shu kanal bo'yicha barcha qoidalar ham o'chadi.",
        reply_markup=confirm_leave(channel_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ch:leaveok:"))
async def cb_leave_ok(cb: CallbackQuery, userbot: TelegramClient) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    channel_id = int(cb.data.split(":", 2)[2])
    try:
        entity = await userbot.get_entity(channel_id)
        await userbot(LeaveChannelRequest(entity))
    except Exception as exc:
        log.exception("leave xato")
        await cb.answer(f"Xato: {exc}", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        await remove_rules_for_channel(session, channel_id=channel_id)
        await session.commit()
    await cb.answer("Chiqildi")
    await _render_channels_list(cb, userbot)


# ---------------- Legacy text commands ----------------


@router.message(Command("channels"))
async def cmd_channels(message: Message, userbot: TelegramClient) -> None:
    if not is_owner_message(message):
        return
    await _render_channels_list(message, userbot)


@router.message(Command("resolve"))
async def cmd_resolve(message: Message, userbot: TelegramClient, command: Any) -> None:
    if not is_owner_message(message):
        return
    if not command.args:
        await message.answer("Foydalanish: /resolve &lt;@username yoki link&gt;")
        return
    entity = await resolve_channel(userbot, command.args.strip())
    if entity is None:
        await message.answer("Kanal topilmadi yoki bu username/invite link emas.")
        return
    await message.answer(
        f"<b>{entity.title}</b>\nid: <code>{channel_id_to_db(entity.id)}</code>\n"
        f"username: @{entity.username or '—'}"
    )


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, userbot: TelegramClient, command: Any) -> None:
    if not is_owner_message(message):
        return
    if not command.args:
        await message.answer("Foydalanish: /subscribe &lt;@username yoki invite link&gt;")
        return
    arg = command.args.strip()
    try:
        if "t.me/+" in arg or "/joinchat/" in arg:
            hash_part = arg.rsplit("+", 1)[-1] if "t.me/+" in arg else arg.rsplit("/", 1)[-1]
            with contextlib.suppress(UserAlreadyParticipantError):
                await userbot(ImportChatInviteRequest(hash_part))
            await message.answer("Obuna bo'lindi (invite link).")
            return
        entity = await userbot.get_entity(arg)
        await userbot(JoinChannelRequest(entity))
        await message.answer(f"Obuna bo'lindi: <b>{getattr(entity, 'title', arg)}</b>")
    except (InviteHashExpiredError, InviteHashInvalidError):
        await message.answer("Invite link yaroqsiz yoki muddati tugagan.")
    except ChannelPrivateError:
        await message.answer("Kanal yopiq — invite link kerak.")
    except FloodWaitError as exc:
        await message.answer(f"Telegram rate limit: {exc.seconds}s kutish kerak.")
    except Exception as exc:
        log.exception("subscribe xato")
        await message.answer(f"Xato: {exc}")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, userbot: TelegramClient, command: Any) -> None:
    if not is_owner_message(message):
        return
    if not command.args:
        await message.answer("Foydalanish: /unsubscribe &lt;@username yoki id&gt;")
        return
    try:
        entity = await userbot.get_entity(command.args.strip())
        await userbot(LeaveChannelRequest(entity))
        await message.answer("Obunadan chiqdim.")
    except Exception as exc:
        log.exception("unsubscribe xato")
        await message.answer(f"Xato: {exc}")


@router.message(Command("link"))
async def cmd_link(message: Message, userbot: TelegramClient, command: Any) -> None:
    """Legacy: /link <kanal> <anime_id>  — bo'sh pattern bilan qoida qo'shadi."""
    if not is_owner_message(message):
        return
    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.answer(
            "Foydalanish: /link &lt;kanal&gt; &lt;anime_id&gt;\n"
            "Murakkabroq qoidalar uchun /menu → Kanallar dan foydalaning."
        )
        return
    channel_raw, anime_raw = parts
    try:
        anime_id = int(anime_raw)
    except ValueError:
        await message.answer("anime_id butun son bo'lishi kerak.")
        return

    try:
        channel_id = int(channel_raw)
    except ValueError:
        entity = await resolve_channel(userbot, channel_raw)
        if entity is None:
            await message.answer("Kanal topilmadi. Avval /subscribe qiling.")
            return
        channel_id = channel_id_to_db(entity.id)

    async with AsyncSessionLocal() as session:
        await add_rule(
            session,
            channel_id=channel_id,
            pattern="",
            pattern_type=PATTERN_SUBSTRING,
            anime_id=anime_id,
            created_by=message.from_user.id if message.from_user else 0,
        )
        await session.commit()
    title = await get_channel_title(userbot, channel_id)
    await message.answer(
        f"Qoida qo'shildi: kanal <code>{channel_id}</code> → anime #{anime_id}"
        + (f" ({title})" if title else "")
    )


@router.message(Command("unlink"))
async def cmd_unlink(message: Message, command: Any) -> None:
    if not is_owner_message(message):
        return
    parts = (command.args or "").split()
    if not parts:
        await message.answer("Foydalanish: /unlink &lt;kanal_id&gt;")
        return
    try:
        channel_id = int(parts[0])
    except ValueError:
        await message.answer("Kanal ID butun son bo'lishi kerak.")
        return
    async with AsyncSessionLocal() as session:
        removed = await remove_rules_for_channel(session, channel_id=channel_id)
        await session.commit()
    await message.answer(f"O'chirildi: {removed} qoida.")
