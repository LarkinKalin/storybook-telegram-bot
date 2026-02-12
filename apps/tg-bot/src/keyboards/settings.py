from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_settings_keyboard(*, add_dev_tools: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="👶 Имя ребёнка", callback_data="settings:child_name")]]
    if add_dev_tools:
        rows.append([InlineKeyboardButton(text="🧪 Тест верстки PDF (быстро)", callback_data="dev:book_layout_test")])
        rows.append([InlineKeyboardButton(text="🧪 Тест rewrite (Kimi)", callback_data="dev:book_rewrite_test")])
        rows.append([InlineKeyboardButton(text="🧪 Тест книги (8 шагов)", callback_data="dev:book_test")])
    rows.append([InlineKeyboardButton(text="⬅ В меню", callback_data="go:l1")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
