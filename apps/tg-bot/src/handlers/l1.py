from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove


from src.handlers.l2 import open_l2
from src.keyboards.l1 import L1Label, build_l1_keyboard
from src.keyboards.why import build_why_keyboard
from src.services.runtime_sessions import has_active, set_active
from src.states import L5, UX

router = Router(name="l1")

# Алиасы команд (slash) -> кнопка L1
# Важно: алиасы делаем БЕЗ эмодзи, чтобы человек мог набрать руками.
L1_ALIASES: dict[str, L1Label] = {
    # Start story (кнопка "▶ Начать сказку")
    "/new": L1Label.START,
    "/begin": L1Label.START,
    "/story": L1Label.START,
    "/start_story": L1Label.START,
    "/начать": L1Label.START,
    "/сказка": L1Label.START,

    # Why (кнопка "🧠 Почемучка")
    "/why": L1Label.WHY,
    "/почему": L1Label.WHY,
    "/почемучка": L1Label.WHY,

    # Continue (кнопка "⏩ Продолжить")
    "/continue": L1Label.CONTINUE,
    "/resume": L1Label.CONTINUE,
    "/продолжить": L1Label.CONTINUE,

    # My (кнопка "🧩 Мои сказки")
    "/my": L1Label.MY,
    "/mine": L1Label.MY,
    "/мои": L1Label.MY,
    "/сохранения": L1Label.MY,

    # Shop (кнопка "🛒 Магазин")
    "/shop": L1Label.SHOP,
    "/store": L1Label.SHOP,
    "/buy": L1Label.SHOP,
    "/магазин": L1Label.SHOP,

    # Help (кнопка "❓ Помощь")
    "/help": L1Label.HELP,
    "/помощь": L1Label.HELP,
    "/info": L1Label.HELP,

    # Settings (кнопка "⚙ Настройки")
    "/settings": L1Label.SETTINGS,
    "/prefs": L1Label.SETTINGS,
    "/настройки": L1Label.SETTINGS,
}


def extract_slash_token(text: str) -> str | None:
    """
    Берём первую "команду" вида /xxx из начала строки.
    Возвращает токен целиком (с /) или None.
    """
    t = text.strip()
    if not t.startswith("/"):
        return None
    # берём до пробела, чтобы "/мага что-то" тоже подсказалось
    return t.split()[0]


def suggest_aliases(prefix: str, limit: int = 6) -> list[str]:
    """
    Подсказки по префиксу: "/мага" -> ["/магазин"].
    Сортируем: короткие и "ближе" к префиксу первыми.
    """
    p = prefix.lower().strip()
    if not p.startswith("/") or len(p) < 2:
        return []

    matches = [k for k in L1_ALIASES.keys() if k.startswith(p)]
    matches.sort(key=lambda x: (len(x), x))
    return matches[:limit]


def normalize_l1_input(text: str) -> str:
    """
    Нормализация ввода в L1:
    - если это slash-команда и она в алиасах -> возвращаем точный label кнопки (с эмодзи)
    - иначе возвращаем текст как есть
    """
    t = text.strip()
    if not t:
        return t

    cmd = extract_slash_token(t)
    if cmd:
        cmd_low = cmd.lower()
        if cmd_low in L1_ALIASES:
            return L1_ALIASES[cmd_low].value

    return t


async def open_l1(message: Message, state: FSMContext) -> None:
    # MVP-правило: только private чат.
    if message.chat.type != "private":
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return

    await state.set_state(UX.l1)
    await message.answer(
        "🏠 Главное меню",
        reply_markup=build_l1_keyboard(has_active(message.from_user.id)),
    )


@router.message(Command("start"))
async def on_start(message: Message, state: FSMContext) -> None:
    # /start = вход в "дом" бота (L1), не "начать сказку"
    await open_l1(message, state)


@router.message(UX.l1)
async def l1_any(message: Message, state: FSMContext) -> None:
    """
    UX-правило:
    - ReplyKeyboard = текст.
    - СНАЧАЛА матчимся по лейблам кнопок (включая алиасы slash-команд).
    - Если пользователь ввёл кусок slash-команды -> показываем подсказки.
    - Потом: неизвестный ввод -> подсказка + повтор L1, без смены состояния.
    """
    if not message.text:
        await message.answer("Мне нужен текст или кнопки. Остальное я не ем.")
        await message.answer(
            "🏠 Главное меню",
            reply_markup=build_l1_keyboard(has_active(message.from_user.id)),
        )
        return

    raw = message.text.strip()

    # Если пользователь начал ввод slash-команды, но не попал целиком,
    # попробуем подсказать похожие команды.
    cmd = extract_slash_token(raw)
    if cmd:
        cmd_low = cmd.lower()
        if cmd_low not in L1_ALIASES:
            suggestions = suggest_aliases(cmd_low)
            if suggestions:
                await message.answer(
                    "Похоже, ты имел в виду:\n" + "\n".join(f"• {s}" for s in suggestions)
                )
                await message.answer(
                    "🏠 Главное меню",
                    reply_markup=build_l1_keyboard(has_active(message.from_user.id)),
                )
                return

    text = normalize_l1_input(raw)

    # 1) СНАЧАЛА: кнопочные команды (строго по лейблам)
    if text == L1Label.START.value:
        set_active(message.from_user.id, True)
        await open_l2(message, state)
        return
    
    if text == L1Label.WHY.value:
        await state.set_state(L5.WHY_TEXT)
        await message.answer(
            "🧠 Почемучка. Задай вопрос текстом (можно надиктовать так, чтобы Telegram вставил текст).",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer("Что тебя интересует?", reply_markup=build_why_keyboard())
        return


    from aiogram.types import ReplyKeyboardRemove
    # (импорт добавь рядом с другими импортами aiogram.types)

    ...

    if text == L1Label.WHY.value:
        await state.set_state(L5.WHY_TEXT)
        await message.answer(
            "🧠 Почемучка. Задай вопрос текстом (можно продиктовать в поле ввода, чтобы получилось текстом).",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer("Что тебя интересует?", reply_markup=build_why_keyboard())
        return


    if text == L1Label.MY.value:
        await message.answer("🧩 Мои сказки → заглушка.")
        await open_l1(message, state)
        return

    if text == L1Label.SHOP.value:
        await message.answer("🛒 Магазин → заглушка.")
        await open_l1(message, state)
        return

    if text == L1Label.HELP.value:
        await message.answer("❓ Помощь → заглушка.")
        await open_l1(message, state)
        return

    if text == L1Label.SETTINGS.value:
        await message.answer("⚙ Настройки → заглушка.")
        await open_l1(message, state)
        return

    # 2) Потом: "произвольный" неизвестный ввод
    await message.answer("Не понял. Используй кнопки меню или команды /start /help.")
    await message.answer(
        "🏠 Главное меню",
        reply_markup=build_l1_keyboard(has_active(message.from_user.id)),
    )
