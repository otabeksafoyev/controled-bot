"""Inline keyboard builders for the control bot UI."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models import AutoReply, ChannelRule


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📺 Kanallar", callback_data="menu:channels")],
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


def channels_list(channel_groups: list[tuple[int, int, str | None]]) -> InlineKeyboardMarkup:
    """channel_groups: list of (channel_id, rules_count, title_or_None)."""
    rows: list[list[InlineKeyboardButton]] = []
    for channel_id, count, title in channel_groups:
        label = title or str(channel_id)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📺 {label} ({count} qoida)",
                    callback_data=f"ch:view:{channel_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="ch:add")])
    rows.append([InlineKeyboardButton(text="◀️ Bosh menyu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_detail(channel_id: int, rules: list[ChannelRule]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for rule in rules:
        preview = _pattern_label(rule.pattern, rule.pattern_type)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 #{rule.id} {preview} → anime #{rule.anime_id}",
                    callback_data=f"rule:delask:{rule.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Qoida qo'shish", callback_data=f"ch:addrule:{channel_id}")])
    rows.append([InlineKeyboardButton(text="🚪 Kanaldan chiqish", callback_data=f"ch:leave:{channel_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Kanallar", callback_data="menu:channels")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete(rule_id: int, channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, o'chir", callback_data=f"rule:delok:{rule_id}"),
                InlineKeyboardButton(text="❌ Bekor", callback_data=f"ch:view:{channel_id}"),
            ]
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


def pattern_type_choice(context: str) -> InlineKeyboardMarkup:
    """context is free text that identifies the wizard (e.g., 'rule', 'reply')."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Oddiy matn", callback_data=f"ptype:{context}:substring"),
                InlineKeyboardButton(text="🧩 Regex", callback_data=f"ptype:{context}:regex"),
            ],
            [InlineKeyboardButton(text="🌐 Barcha videolar", callback_data=f"ptype:{context}:all")],
            [InlineKeyboardButton(text="❌ Bekor", callback_data="wiz:cancel")],
        ]
    )


def wizard_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor", callback_data="wiz:cancel")]]
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
            [
                InlineKeyboardButton(text=toggle_text, callback_data=f"ar:toggle:{reply.id}"),
                InlineKeyboardButton(text="🗑 O'chir", callback_data=f"ar:delask:{reply.id}"),
            ],
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
        return "«istalgan»"
    preview = pattern[:24] + ("…" if len(pattern) > 24 else "")
    tag = "re" if pattern_type == "regex" else "txt"
    return f"[{tag}] {preview}"
