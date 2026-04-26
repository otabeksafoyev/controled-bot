"""Channel management — subscribe / unsubscribe only. No per-channel rules.

Animedan qism yuborish kaworai DB orqali avtomatik bo'ladi (userbot/handlers.py).
"""

from __future__ import annotations

import contextlib
import logging

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
    confirm_leave,
    wizard_cancel,
)
from bot.states import AddChannelStates
from db.engine import AsyncSessionLocal
from db.queries import (
    add_channel,
    get_channel,
    list_channels,
    remove_channel,
)

log = logging.getLogger(__name__)
router = Router(name="channels")
router.message.filter(F.chat.type == "private")


# ---------------- List + view ----------------


async def _render_list(message_or_cb: Message | CallbackQuery, userbot: TelegramClient) -> None:
    async with AsyncSessionLocal() as session:
        channels = await list_channels(session)

    # Yangilab ketsin: agar title yo'q bo'lsa, Telethon'dan olamiz.
    for c in channels:
        if not c.title:
            title = await get_channel_title(userbot, c.channel_id)
            if title:
                async with AsyncSessionLocal() as session:
                    row = await get_channel(session, c.channel_id)
                    if row is not None:
                        row.title = title
                        await session.commit()
                c.title = title

    text = "<b>Kanallar</b>\n\n" + (
        "Hozir kuzatilayotgan kanal yo'q.\n\n" "➕ Kanal qo'shish tugmasini bosing."
        if not channels
        else "Kuzatilayotgan kanallar ro'yxati. Qo'shimcha qoida sozlash shart emas —\n"
        "anime nomi caption-dan kaworai DB-dan avtomatik aniqlanadi."
    )
    kb = channels_list(channels)
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
    await _render_list(cb, userbot)


@router.callback_query(F.data.startswith("ch:view:"))
async def cb_view_channel(cb: CallbackQuery, userbot: TelegramClient, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    await state.clear()
    msg = accessible(cb)
    if msg is None:
        return
    channel_id = int(cb.data.split(":", 2)[2])
    async with AsyncSessionLocal() as session:
        row = await get_channel(session, channel_id)
    title = (row.title if row else None) or await get_channel_title(userbot, channel_id) or str(channel_id)
    username = row.username if row else None
    lines = [
        f"<b>{title}</b>",
        f"ID: <code>{channel_id}</code>",
    ]
    if username:
        lines.append(f"@{username}")
    lines.append("")
    lines.append("Kanaldan video avtomatik olinadi va caption-dagi anime nomiga qarab")
    lines.append("kaworai SECRET_CHANNEL ga yuboriladi.")
    await msg.edit_text("\n".join(lines), reply_markup=channel_detail(channel_id))
    await cb.answer()


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
async def on_add_channel_input(
    message: Message,
    state: FSMContext,
    userbot: TelegramClient,
) -> None:
    if not is_owner_message(message):
        return
    raw = (message.text or "").strip()
    if not raw:
        await message.answer("Bo'sh xabar. @username yoki invite link yuboring.")
        return

    channel_id, title, username = await _subscribe(userbot, raw)
    if channel_id is None:
        await message.answer("Kanalni topa olmadim yoki kirishga ruxsat yo'q.", reply_markup=back_to_main())
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        await add_channel(
            session,
            channel_id=channel_id,
            title=title,
            username=username,
            added_by=message.from_user.id if message.from_user else 0,
        )
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>{title or channel_id}</b> qo'shildi.\n\n"
        "Shu kanalga video kelganda caption bo'yicha anime avtomatik aniqlanadi.",
        reply_markup=back_to_main(),
    )


async def _subscribe(userbot: TelegramClient, raw: str) -> tuple[int | None, str | None, str | None]:
    """Invite link yoki @username bo'yicha kanalga qo'shiladi.

    Return: (channel_id_db, title, username) yoki (None, None, None) xato bo'lsa.
    """
    try:
        if "t.me/+" in raw or "t.me/joinchat/" in raw:
            hash_part = raw.rsplit("/", 1)[-1].lstrip("+")
            try:
                updates = await userbot(ImportChatInviteRequest(hash_part))
            except UserAlreadyParticipantError:
                entity = await userbot.get_entity(raw)
                return (
                    channel_id_to_db(entity.id),
                    getattr(entity, "title", None),
                    getattr(entity, "username", None),
                )
            except (InviteHashExpiredError, InviteHashInvalidError):
                return None, None, None
            chats = getattr(updates, "chats", []) or []
            if not chats:
                return None, None, None
            chat = chats[0]
            return channel_id_to_db(chat.id), getattr(chat, "title", None), getattr(chat, "username", None)

        entity = await resolve_channel(userbot, raw)
        if entity is None:
            return None, None, None
        with contextlib.suppress(UserAlreadyParticipantError, ChannelPrivateError, FloodWaitError):
            await userbot(JoinChannelRequest(entity))
        return channel_id_to_db(entity.id), getattr(entity, "title", None), getattr(entity, "username", None)
    except Exception as exc:
        log.warning("Subscribe xato: %s", exc)
        return None, None, None


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
        f"Kanaldan chiqib, kuzatuvni to'xtatasizmi?\nID: <code>{channel_id}</code>",
        reply_markup=confirm_leave(channel_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("ch:leaveok:"))
async def cb_leave_ok(cb: CallbackQuery, userbot: TelegramClient) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    channel_id = int(cb.data.split(":", 2)[2])
    async with AsyncSessionLocal() as session:
        await remove_channel(session, channel_id=channel_id)
        await session.commit()
    with contextlib.suppress(Exception):
        entity = await userbot.get_entity(channel_id)
        await userbot(LeaveChannelRequest(entity))
    await cb.answer("Chiqildi")
    await _render_list(cb, userbot)


# ---------------- Legacy text commands (backwards compat) ----------------


@router.message(Command("channels"))
async def cmd_channels(message: Message, userbot: TelegramClient) -> None:
    if not is_owner_message(message):
        return
    async with AsyncSessionLocal() as session:
        channels = await list_channels(session)
    if not channels:
        await message.answer("Hozir kanal yo'q. /menu dan qo'shing.")
        return
    lines = ["<b>Kanallar</b>"]
    for c in channels:
        title = c.title or await get_channel_title(userbot, c.channel_id) or str(c.channel_id)
        lines.append(f"• <code>{c.channel_id}</code> — {title}")
    await message.answer("\n".join(lines))


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, userbot: TelegramClient) -> None:
    if not is_owner_message(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Foydalanish: /subscribe @kanal  yoki  /subscribe https://t.me/+abc")
        return
    channel_id, title, username = await _subscribe(userbot, parts[1].strip())
    if channel_id is None:
        await message.answer("Kanalni topa olmadim.")
        return
    async with AsyncSessionLocal() as session:
        await add_channel(
            session,
            channel_id=channel_id,
            title=title,
            username=username,
            added_by=message.from_user.id if message.from_user else 0,
        )
        await session.commit()
    await message.answer(f"✅ {title or channel_id} qo'shildi. ID: <code>{channel_id}</code>")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message, userbot: TelegramClient) -> None:
    if not is_owner_message(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Foydalanish: /unsubscribe <channel_id yoki @username>")
        return
    raw = parts[1].strip()
    channel_id: int | None = None
    try:
        channel_id = int(raw)
    except ValueError:
        entity = await resolve_channel(userbot, raw)
        if entity is not None:
            channel_id = channel_id_to_db(entity.id)
    if channel_id is None:
        await message.answer("Topilmadi.")
        return
    async with AsyncSessionLocal() as session:
        removed = await remove_channel(session, channel_id=channel_id)
        await session.commit()
    await message.answer(f"{'✅ O‘chirildi' if removed else 'Topilmadi'}: <code>{channel_id}</code>")


@router.message(Command("resolve"))
async def cmd_resolve(message: Message, userbot: TelegramClient) -> None:
    if not is_owner_message(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Foydalanish: /resolve @kanal")
        return
    entity = await resolve_channel(userbot, parts[1].strip())
    if entity is None:
        await message.answer("Topilmadi.")
        return
    title = getattr(entity, "title", None) or "?"
    username = getattr(entity, "username", None)
    uname = f"@{username}" if username else "(username yo'q)"
    await message.answer(f"<b>{title}</b>\nID: <code>{channel_id_to_db(entity.id)}</code>\n{uname}")
