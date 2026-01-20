from __future__ import annotations

from enum import Enum

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


class L1Label(str, Enum):
    # ВАЖНО: тексты = константы из UX-10. Менять emoji/пробелы нельзя.
    START = "▶ Начать сказку"
    WHY = "🧠 Почемучка"
    CONTINUE = "⏩ Продолжить"
    MY = "🧩 Мои сказки"
    SHOP = "🛒 Магазин"
    HELP = "❓ Помощь"
    SETTINGS = "⚙ Настройки"


L1_LABELS_SET: set[str] = {x.value for x in L1Label}


def build_l1_keyboard(has_active: bool) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [
            KeyboardButton(text=L1Label.START.value),
            KeyboardButton(text=L1Label.WHY.value),
        ],
    ]

    # По UX-10: "⏩ Продолжить" показывать только если есть ACTIVE.
    if has_active:
        rows.append([KeyboardButton(text=L1Label.CONTINUE.value)])

    rows.append(
        [
            KeyboardButton(text=L1Label.MY.value),
            KeyboardButton(text=L1Label.SHOP.value),
        ]
    )
    rows.append(
        [
            KeyboardButton(text=L1Label.HELP.value),
            KeyboardButton(text=L1Label.SETTINGS.value),
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери кнопку (или /help)",
    )
