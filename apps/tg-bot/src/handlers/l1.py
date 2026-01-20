from __future__ import annotations

from time import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from src.handlers.l2 import open_l2
from src.keyboards.l1 import L1Label, build_l1_keyboard
from src.keyboards.help import build_help_keyboard
from src.keyboards.l3 import build_l3_keyboard
from src.keyboards.shop import build_shop_keyboard
from src.keyboards.why import build_why_keyboard
from src.services.runtime_sessions import abort_session, get_session, has_active, touch_last_step
from src.services.theme_registry import registry
from src.states import L3, L4, L5, UX

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


def _is_private(message: Message) -> bool:
    return message.chat.type == "private"


async def _send_help_screen(message: Message) -> None:
    sent = await message.answer(
        "❓ Помощь\n\nЗдесь будет помощь по боту.",
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await message.bot.edit_message_reply_markup(
            chat_id=sent.chat.id,
            message_id=sent.message_id,
            reply_markup=build_help_keyboard(),
        )
    except Exception:
        pass


async def _send_shop_screen(message: Message) -> None:
    sent = await message.answer(
        "🛒 Магазин скоро, оплаты в MVP нет.",
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await message.bot.edit_message_reply_markup(
            chat_id=sent.chat.id,
            message_id=sent.message_id,
            reply_markup=build_shop_keyboard(),
        )
    except Exception:
        pass


def _is_session_valid(session: object) -> bool:
    if not session:
        return False
    if getattr(session, "theme_id", None) is None:
        return False
    step = getattr(session, "step", None)
    max_steps = getattr(session, "max_steps", None)
    return isinstance(step, int) and isinstance(max_steps, int)


async def do_continue(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return

    if not has_active(message.from_user.id):
        await message.answer("Нет активной сказки. Нажми ▶ Начать сказку.")
        await open_l1(message, state)
        return

    session = get_session(message.from_user.id)
    if not _is_session_valid(session):
        abort_session(message.from_user.id)
        await message.answer("Сессия потерялась. Начни заново.")
        await open_l1(message, state)
        return

    now_ts = int(time())
    if session.last_step_sent_at and now_ts - session.last_step_sent_at < 5:
        await open_l1(message, state)
        return

    if session.last_step_message_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=session.last_step_message_id,
                reply_markup=None,
            )
        except Exception:
            pass

    theme_title = session.theme_id
    theme = registry.get_theme(session.theme_id) if session.theme_id else None
    if theme:
        theme_title = theme["title"]

    step_ui = session.step + 1
    step_text = (
        f"Продолжаем: Шаг {step_ui}/{session.max_steps}. "
        f"Тема: {theme_title}. История появится в следующем квесте."
    )
    sent_message = await message.answer(step_text, reply_markup=ReplyKeyboardRemove())
    try:
        await message.bot.edit_message_reply_markup(
            chat_id=sent_message.chat.id,
            message_id=sent_message.message_id,
            reply_markup=build_l3_keyboard(),
        )
    except Exception:
        pass
    touch_last_step(message.from_user.id, sent_message.message_id, now_ts)
    await state.set_state(L3.STEP)


@router.message(Command("resume"))
async def on_resume(message: Message, state: FSMContext) -> None:
    await do_continue(message, state)


@router.message(Command("status"))
async def on_status(message: Message) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return

    session = get_session(message.from_user.id)
    active = has_active(message.from_user.id)
    lines = [f"active: {'yes' if active else 'no'}"]
    if active and _is_session_valid(session):
        lines.append(f"step_ui: {session.step + 1}")
        lines.append(f"max_steps: {session.max_steps}")
        theme_title = session.theme_id
        theme = registry.get_theme(session.theme_id) if session.theme_id else None
        if theme:
            theme_title = theme["title"]
        if theme_title:
            lines.append(f"theme: {theme_title}")
    elif active:
        lines.append("step_ui: unknown")
        lines.append("max_steps: unknown")
        lines.append("theme: unknown")
        abort_session(message.from_user.id)
    await message.answer("\n".join(lines))


@router.message(Command("help"))
async def on_help(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return
    await state.set_state(L4.HELP)
    await _send_help_screen(message)


@router.message(Command("shop"))
async def on_shop(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return
    await state.set_state(L4.SHOP)
    await _send_shop_screen(message)


@router.callback_query(lambda query: query.data == "go:l1")
async def on_go_l1(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await open_l1(callback.message, state)
    await callback.answer()


@router.callback_query(lambda query: query.data == "go:help")
async def on_go_help(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    if callback.message.chat.type != "private":
        await callback.message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        await callback.answer()
        return
    await state.set_state(L4.HELP)
    await _send_help_screen(callback.message)
    await callback.answer()


@router.callback_query(lambda query: query.data == "go:shop")
async def on_go_shop(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    if callback.message.chat.type != "private":
        await callback.message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        await callback.answer()
        return
    await state.set_state(L4.SHOP)
    await _send_shop_screen(callback.message)
    await callback.answer()


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
        await open_l2(message, state)
        return

    if text == L1Label.WHY.value:
        await state.set_state(L5.WHY_TEXT)
        await message.answer(
            "Задай вопрос — попробую объяснить простыми словами.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer("Что тебя интересует?", reply_markup=build_why_keyboard())
        return

    if text == L1Label.CONTINUE.value:
        await do_continue(message, state)
        return


    if text == L1Label.MY.value:
        await message.answer("🧩 Мои сказки → заглушка.")
        await open_l1(message, state)
        return

    if text == L1Label.SHOP.value:
        await state.set_state(L4.SHOP)
        await _send_shop_screen(message)
        return

    if text == L1Label.HELP.value:
        await state.set_state(L4.HELP)
        await _send_help_screen(message)
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
