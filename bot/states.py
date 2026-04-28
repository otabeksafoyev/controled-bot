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


class AddWorkoutStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_media = State()


class AddScheduleStates(StatesGroup):
    waiting_for_days = State()
    waiting_for_time = State()
    waiting_for_timeout = State()


class AddExerciseStates(StatesGroup):
    """Mashq ichiga element qo'shish wizard."""

    waiting_for_name = State()
    waiting_for_spec = State()
    waiting_for_description = State()
    waiting_for_media = State()


class EditExerciseStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_spec = State()
    waiting_for_description = State()


class AddExerciseMediaStates(StatesGroup):
    waiting_for_media = State()


class ImportTimesStates(StatesGroup):
    """Import-dan keyin har kunga vaqt biriktirish wizard."""

    waiting_for_time = State()


class WeekDayAddStates(StatesGroup):
    """Adding a workout to a specific day from the weekly view."""

    waiting_for_new_name = State()
    waiting_for_new_description = State()
    waiting_for_new_media = State()
    waiting_for_time = State()
    waiting_for_timeout = State()
