"""Inline keyboard builders for the control bot UI."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models import AutoReply, Channel


def main_menu(pending_count: int = 0) -> InlineKeyboardMarkup:
    pending_label = f"⏳ Kutilayotgan ({pending_count})" if pending_count else "⏳ Kutilayotgan"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📺 Kanallar", callback_data="menu:channels")],
            [InlineKeyboardButton(text=pending_label, callback_data="menu:pending")],
            [InlineKeyboardButton(text="💬 Avtojavoblar", callback_data="menu:replies")],
            [
                InlineKeyboardButton(text="⚙️ Holat", callback_data="menu:status"),
                InlineKeyboardButton(text="📜 So'nggi", callback_data="menu:forwarded"),
            ],
            [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="menu:help")],
        ]
    )


def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Bosh menyu", callback_data="menu:main")]]
    )


def channels_list(channels: list[Channel]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in channels:
        label = c.title or (f"@{c.username}" if c.username else str(c.channel_id))
        status = "🟢" if c.active else "⚪"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {label}",
                    callback_data=f"ch:view:{c.channel_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="ch:add")])
    rows.append([InlineKeyboardButton(text="◀️ Bosh menyu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_detail(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 Kanaldan chiqish", callback_data=f"ch:leave:{channel_id}")],
            [InlineKeyboardButton(text="◀️ Kanallar", callback_data="menu:channels")],
        ]
    )


def confirm_leave(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, chiqish", callback_data=f"ch:leaveok:{channel_id}"),
                InlineKeyboardButton(text="❌ Bekor", callback_data=f"ch:view:{channel_id}"),
            ]
        ]
    )


def wizard_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor", callback_data="wiz:cancel")]]
    )


# -------- Pending --------


def pending_actions(pending_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Nom bilan izlash", callback_data=f"pnd:search:{pending_id}"),
                InlineKeyboardButton(text="✍️ ID kiritish", callback_data=f"pnd:manual:{pending_id}"),
            ],
            [InlineKeyboardButton(text="⛔ O'tkazib yuborish", callback_data=f"pnd:skip:{pending_id}")],
        ]
    )


def pending_list(rows: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    for pid, label in rows:
        kb.append([InlineKeyboardButton(text=label, callback_data=f"pnd:view:{pid}")])
    kb.append([InlineKeyboardButton(text="◀️ Bosh menyu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def pending_search_results(pending_id: int, rows: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    for anime_id, title in rows:
        label = f"#{anime_id} — {title}"
        if len(label) > 60:
            label = label[:57] + "…"
        kb.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"pnd:pick:{pending_id}:{anime_id}",
                )
            ]
        )
    kb.append(
        [
            InlineKeyboardButton(text="🔁 Qaytadan izlash", callback_data=f"pnd:search:{pending_id}"),
            InlineKeyboardButton(text="✍️ ID kiritish", callback_data=f"pnd:manual:{pending_id}"),
        ]
    )
    kb.append([InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"pnd:view:{pending_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def pending_view(pending_id: int, has_episode: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="🔍 Nom bilan izlash", callback_data=f"pnd:search:{pending_id}"),
            InlineKeyboardButton(text="✍️ ID kiritish", callback_data=f"pnd:manual:{pending_id}"),
        ],
    ]
    if not has_episode:
        rows.append(
            [InlineKeyboardButton(text="🔢 Qism raqami kiritish", callback_data=f"pnd:ep:{pending_id}")]
        )
    rows.append([InlineKeyboardButton(text="⛔ O'tkazib yuborish", callback_data=f"pnd:skip:{pending_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Ro'yxat", callback_data="menu:pending")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# -------- Auto-replies --------


def pattern_type_choice(context: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Oddiy matn", callback_data=f"ptype:{context}:substring"),
                InlineKeyboardButton(text="🧩 Regex", callback_data=f"ptype:{context}:regex"),
            ],
            [InlineKeyboardButton(text="🌐 Barcha xabarlar", callback_data=f"ptype:{context}:all")],
            [InlineKeyboardButton(text="❌ Bekor", callback_data="wiz:cancel")],
        ]
    )


def replies_list(replies: list[AutoReply]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in replies:
        preview = _pattern_label(r.pattern, r.pattern_type)
        state = "🟢" if r.active else "⚪"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{state} #{r.id} {preview}",
                    callback_data=f"ar:view:{r.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Yangi avtojavob", callback_data="ar:add")])
    rows.append([InlineKeyboardButton(text="◀️ Bosh menyu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reply_detail(reply: AutoReply) -> InlineKeyboardMarkup:
    toggle_text = "🔴 O'chirish" if reply.active else "🟢 Yoqish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"ar:toggle:{reply.id}")],
            [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"ar:delask:{reply.id}")],
            [InlineKeyboardButton(text="◀️ Avtojavoblar", callback_data="menu:replies")],
        ]
    )


def confirm_delete_reply(reply_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, o'chir", callback_data=f"ar:delok:{reply_id}"),
                InlineKeyboardButton(text="❌ Bekor", callback_data=f"ar:view:{reply_id}"),
            ]
        ]
    )


def _pattern_label(pattern: str, pattern_type: str) -> str:
    if not pattern:
        return "«barchasi»"
    prefix = "🧩 " if pattern_type == "regex" else ""
    short = pattern if len(pattern) <= 28 else pattern[:25] + "…"
    return f"{prefix}{short}"
