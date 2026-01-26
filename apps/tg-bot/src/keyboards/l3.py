from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_l3_keyboard(
    choices: list[dict],
    allow_free_text: bool,
    sid8: str,
    step: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if choices:
        choice_buttons = [
            InlineKeyboardButton(
                text=choice["label"],
                callback_data=f"l3:choice:{choice['choice_id']}:{sid8}:{step}",
            )
            for choice in choices
        ]
        rows.append(choice_buttons)
    if allow_free_text:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✍️ Свой вариант",
                    callback_data=f"l3:free_text:{sid8}:{step}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅ В меню", callback_data="go:l1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_locked_keyboard(
    rows: list[list[dict]],
    sid8: str,
    step: int,
) -> InlineKeyboardMarkup:
    locked_rows: list[list[InlineKeyboardButton]] = []
    for row in rows:
        locked_row: list[InlineKeyboardButton] = []
        for button in row:
            choice_id = button.get("choice_id", "locked")
            locked_row.append(
                InlineKeyboardButton(
                    text=button["text"],
                    callback_data=f"locked:{sid8}:{step}:{choice_id}",
                )
            )
        locked_rows.append(locked_row)
    return InlineKeyboardMarkup(inline_keyboard=locked_rows)


def build_final_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🏠 В меню", callback_data="go:l1")],
        [InlineKeyboardButton(text="▶ Начать новую", callback_data="go:start")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
