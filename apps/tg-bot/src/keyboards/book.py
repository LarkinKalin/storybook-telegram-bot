from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_book_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Посмотреть образец", callback_data="book:sample")],
            [InlineKeyboardButton(text="📖 Купить книгу", callback_data="book:buy")],
            [InlineKeyboardButton(text="⬅ В меню", callback_data="go:l1")],
        ]
    )
