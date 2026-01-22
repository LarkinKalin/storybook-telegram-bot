from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_new_story_confirm_keyboard(theme_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, начать новую", callback_data=f"new:yes:{theme_id}"),
                InlineKeyboardButton(text="❌ Нет, в меню", callback_data="go:l1"),
            ],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="go:l2")],
        ]
    )
