from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.services.theme_registry import registry


def build_l2_keyboard(page_index: int, page_count: int) -> InlineKeyboardMarkup:
    themes = registry.list_themes()
    if not themes:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]]
        )

    page_size = 10
    start = page_index * page_size
    end = start + page_size
    page_themes = themes[start:end]

    rows: list[list[InlineKeyboardButton]] = []
    for theme in page_themes:
        rows.append([InlineKeyboardButton(text=theme["title"], callback_data=f"t:{theme['id']}")])

    if page_count > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page_index > 0:
            nav_row.append(
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pg2:{page_index - 1}")
            )
        if page_index < page_count - 1:
            nav_row.append(
                InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"pg2:{page_index + 1}")
            )
        if nav_row:
            rows.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)
