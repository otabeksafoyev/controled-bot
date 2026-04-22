"""FSM state groups for multi-step wizards."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AddChannelStates(StatesGroup):
    waiting_for_channel = State()


class AddRuleStates(StatesGroup):
    waiting_for_pattern_type = State()
    waiting_for_pattern = State()
    waiting_for_anime_id = State()


class AddReplyStates(StatesGroup):
    waiting_for_pattern_type = State()
    waiting_for_pattern = State()
    waiting_for_reply_text = State()
