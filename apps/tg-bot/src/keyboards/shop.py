from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_shop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❓ Помощь", callback_data="go:help"),
                InlineKeyboardButton(text="⬅ В меню", callback_data="go:l1"),
            ],
        ]
    )
