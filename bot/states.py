"""FSM state groups for multi-step wizards."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddChannelStates(StatesGroup):
    waiting_for_channel = State()


class AddReplyStates(StatesGroup):
    waiting_for_pattern_type = State()
    waiting_for_pattern = State()
    waiting_for_reply_text = State()


class PendingStates(StatesGroup):
    """Owner pending videoni qo'lda hal qilayotgan vaqti."""

    waiting_for_search = State()  # anime nom bo'yicha qidirish matni
    waiting_for_anime_id = State()  # qo'lda ID kiritish
    waiting_for_episode = State()  # qism raqami (agar topilmagan bo'lsa)
