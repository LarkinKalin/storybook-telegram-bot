from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👶 Имя ребёнка", callback_data="settings:child_name")],
            [InlineKeyboardButton(text="⬅ В меню", callback_data="go:l1")],
        ]
    )
