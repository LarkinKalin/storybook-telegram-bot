from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_l3_keyboard(choices: list[dict], allow_free_text: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if choices:
        choice_buttons = [
            InlineKeyboardButton(
                text=choice["label"], callback_data=f"l3:choice:{choice['choice_id']}"
            )
            for choice in choices
        ]
        rows.append(choice_buttons)
    if allow_free_text:
        rows.append(
            [InlineKeyboardButton(text="✍️ Свой вариант", callback_data="l3:free_text")]
        )
    rows.append([InlineKeyboardButton(text="⬅ В меню", callback_data="go:l1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
