"""Pending video handlers — owner qo'lda anime_id biriktiradi yoki skip qiladi."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from telethon import TelegramClient

from bot.common import accessible, is_owner_callback, is_owner_message
from bot.keyboards import (
    back_to_main,
    pending_list,
    pending_search_results,
    pending_view,
    wizard_cancel,
)
from bot.states import PendingStates
from config import settings
from db.engine import AsyncSessionLocal
from db.queries import (
    count_pending,
    get_pending,
    is_forwarded,
    list_pending,
    mark_forwarded,
    remove_pending,
)
from kaworai.queries import episode_exists, get_anime_by_id, search_animes

log = logging.getLogger(__name__)
router = Router(name="pending")
router.message.filter(F.chat.type == "private")


async def _render_list(cb: CallbackQuery) -> None:
    msg = accessible(cb)
    if msg is None:
        return
    async with AsyncSessionLocal() as session:
        rows = await list_pending(session, limit=50)
    if not rows:
        await msg.edit_text(
            "<b>Kutilayotgan videolar</b>\n\nBo'sh — hammasi avtomatik yuborildi.",
            reply_markup=back_to_main(),
        )
        await cb.answer()
        return
    buttons: list[tuple[int, str]] = []
    for r in rows:
        title = (r.caption or "")[:40].replace("\n", " ") or "(caption yo'q)"
        ep = f" ep={r.detected_episode}" if r.detected_episode is not None else ""
        buttons.append((r.id, f"#{r.id}{ep}: {title}"))
    await msg.edit_text(
        f"<b>Kutilayotgan videolar</b> ({len(rows)})\n\nQo'lda anime biriktirish uchun tanlang:",
        reply_markup=pending_list(buttons),
    )
    await cb.answer()


@router.callback_query(F.data == "menu:pending")
async def cb_menu_pending(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb):
        await cb.answer("Ruxsat yo'q", show_alert=True)
        return
    await state.clear()
    await _render_list(cb)


async def _render_item(cb: CallbackQuery, pending_id: int) -> None:
    msg = accessible(cb)
    if msg is None:
        return
    async with AsyncSessionLocal() as session:
        row = await get_pending(session, pending_id)
    if row is None:
        await cb.answer("Topilmadi", show_alert=True)
        await _render_list(cb)
        return
    cap = (row.caption or "").strip() or "(bo'sh)"
    if len(cap) > 400:
        cap = cap[:400] + "…"
    lines = [
        f"<b>Kutilayotgan #{row.id}</b>",
        f"Kanal: <code>{row.source_channel_id}</code>",
        f"Sabab: <i>{row.reason}</i>",
    ]
    if row.detected_episode is not None:
        lines.append(f"Qism: <b>{row.detected_episode}</b>")
    lines.append("")
    lines.append(f"Caption:\n{cap}")
    await msg.edit_text(
        "\n".join(lines),
        reply_markup=pending_view(row.id, has_episode=row.detected_episode is not None),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pnd:view:"))
async def cb_pnd_view(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    await state.clear()
    pid = int(cb.data.split(":", 2)[2])
    await _render_item(cb, pid)


# -------- Skip --------


@router.callback_query(F.data.startswith("pnd:skip:"))
async def cb_pnd_skip(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    pid = int(cb.data.split(":", 2)[2])
    async with AsyncSessionLocal() as session:
        await remove_pending(session, pending_id=pid)
        await session.commit()
    await state.clear()
    await cb.answer("O'tkazib yuborildi")
    msg = accessible(cb)
    if msg is not None:
        await msg.edit_text("⛔ O'tkazib yuborildi.", reply_markup=back_to_main())


# -------- Search --------


@router.callback_query(F.data.startswith("pnd:search:"))
async def cb_pnd_search(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    pid = int(cb.data.split(":", 2)[2])
    msg = accessible(cb)
    if msg is None:
        return
    await state.set_state(PendingStates.waiting_for_search)
    await state.update_data(pending_id=pid)
    await msg.edit_text(
        "🔍 Anime nomini kiriting (qisman ham bo'ladi, masalan: <code>klever</code>):",
        reply_markup=wizard_cancel(),
    )
    await cb.answer()


@router.message(PendingStates.waiting_for_search)
async def on_search_input(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    data = await state.get_data()
    pid = int(data.get("pending_id") or 0)
    if not pid:
        await state.clear()
        return
    query = (message.text or "").strip()
    if not query:
        await message.answer("Bo'sh so'rov.")
        return
    results = await search_animes(query, limit=10)
    if not results:
        await message.answer(
            f"Hech narsa topilmadi: <code>{query}</code>. Qaytadan yozing yoki ID kiriting.",
        )
        return
    rows = [(a.id, a.title) for a in results]
    await state.clear()
    await message.answer(
        f"So'rov: <code>{query}</code>\nNatijalar:",
        reply_markup=pending_search_results(pid, rows),
    )


# -------- Manual ID --------


@router.callback_query(F.data.startswith("pnd:manual:"))
async def cb_pnd_manual(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    pid = int(cb.data.split(":", 2)[2])
    msg = accessible(cb)
    if msg is None:
        return
    await state.set_state(PendingStates.waiting_for_anime_id)
    await state.update_data(pending_id=pid)
    await msg.edit_text("✍️ Anime ID raqamini kiriting:", reply_markup=wizard_cancel())
    await cb.answer()


@router.message(PendingStates.waiting_for_anime_id)
async def on_manual_id(message: Message, state: FSMContext, userbot: TelegramClient, bot: Bot) -> None:
    if not is_owner_message(message):
        return
    data = await state.get_data()
    pid = int(data.get("pending_id") or 0)
    if not pid:
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        anime_id = int(raw)
    except ValueError:
        await message.answer("Raqam emas. Qaytadan kiriting.")
        return
    await _resolve_pending(message, state, userbot, bot, pending_id=pid, anime_id=anime_id)


# -------- Pick from search results --------


@router.callback_query(F.data.startswith("pnd:pick:"))
async def cb_pnd_pick(cb: CallbackQuery, state: FSMContext, userbot: TelegramClient, bot: Bot) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    parts = cb.data.split(":")
    if len(parts) < 4:
        return
    pid = int(parts[2])
    anime_id = int(parts[3])
    msg = accessible(cb)
    if msg is None:
        return
    await _resolve_pending(msg, state, userbot, bot, pending_id=pid, anime_id=anime_id)
    await cb.answer()


# -------- Episode input --------


@router.callback_query(F.data.startswith("pnd:ep:"))
async def cb_pnd_ep(cb: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_callback(cb) or cb.data is None:
        return
    pid = int(cb.data.split(":", 2)[2])
    msg = accessible(cb)
    if msg is None:
        return
    await state.set_state(PendingStates.waiting_for_episode)
    await state.update_data(pending_id=pid)
    await msg.edit_text("🔢 Qism raqamini kiriting:", reply_markup=wizard_cancel())
    await cb.answer()


@router.message(PendingStates.waiting_for_episode)
async def on_episode_input(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return
    data = await state.get_data()
    pid = int(data.get("pending_id") or 0)
    if not pid:
        await state.clear()
        return
    try:
        ep = int((message.text or "").strip())
    except ValueError:
        await message.answer("Raqam emas. Qaytadan kiriting.")
        return
    async with AsyncSessionLocal() as session:
        row = await get_pending(session, pid)
        if row is None:
            await state.clear()
            await message.answer("Topilmadi.")
            return
        row.detected_episode = ep
        await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Qism: <b>{ep}</b> saqlandi. Endi anime-ni biriktiring.",
        reply_markup=back_to_main(),
    )


# -------- Resolve (forward) --------


async def _resolve_pending(
    target: Message,
    state: FSMContext,
    userbot: TelegramClient,
    bot: Bot,
    *,
    pending_id: int,
    anime_id: int,
) -> None:
    await state.clear()
    async with AsyncSessionLocal() as session:
        row = await get_pending(session, pending_id)
    if row is None:
        await target.answer("Topilmadi.", reply_markup=back_to_main())
        return

    if row.detected_episode is None:
        await target.answer(
            "Qism raqami yo'q — avval <b>🔢 Qism raqami</b> tugmasi orqali kiriting.",
            reply_markup=back_to_main(),
        )
        return

    anime = await get_anime_by_id(anime_id)
    title = anime.title if anime else None

    episode = row.detected_episode

    if await episode_exists(anime_id, episode):
        async with AsyncSessionLocal() as session:
            await mark_forwarded(
                session,
                file_unique_id=row.file_unique_id,
                anime_id=anime_id,
                episode=episode,
                source_channel_id=row.source_channel_id,
            )
            await remove_pending(session, pending_id=row.id)
            await session.commit()
        await target.answer(
            f"ℹ️ <b>{title or anime_id}</b> qism {episode} kaworai DB-da bor — skip qilindi.",
            reply_markup=back_to_main(),
        )
        return

    async with AsyncSessionLocal() as session:
        if await is_forwarded(session, row.file_unique_id):
            await remove_pending(session, pending_id=row.id)
            await session.commit()
            await target.answer("Allaqachon yuborilgan.", reply_markup=back_to_main())
            return

    try:
        msg = await userbot.get_messages(row.source_channel_id, ids=row.source_message_id)
        if msg is None or getattr(msg, "media", None) is None:
            raise RuntimeError("Asl xabar topilmadi yoki media yo'q")
        await userbot.send_file(
            settings.SECRET_CHANNEL_ID,
            file=msg.media,
            caption=f"ID: {anime_id}\nQism: {episode}",
        )
    except Exception as exc:
        log.exception("Pending resolve forward xato pending=%s", pending_id)
        await target.answer(f"❌ Yuborishda xato: <code>{exc}</code>", reply_markup=back_to_main())
        return

    async with AsyncSessionLocal() as session:
        await mark_forwarded(
            session,
            file_unique_id=row.file_unique_id,
            anime_id=anime_id,
            episode=episode,
            source_channel_id=row.source_channel_id,
        )
        await remove_pending(session, pending_id=row.id)
        await session.commit()

    await target.answer(
        f"✅ Yuborildi: <b>{title or anime_id}</b> — qism {episode}",
        reply_markup=back_to_main(),
    )


async def get_pending_count() -> int:
    async with AsyncSessionLocal() as session:
        return await count_pending(session)
