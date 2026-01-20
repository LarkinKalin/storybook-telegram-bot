from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🛒 Магазин", callback_data="go:shop"),
                InlineKeyboardButton(text="⬅ В меню", callback_data="go:l1"),
            ],
        ]
    )
