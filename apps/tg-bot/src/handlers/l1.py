from __future__ import annotations

import logging
from time import time

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from src.handlers.l2 import open_l2
from src.keyboards.l1 import L1Label, build_l1_keyboard
from src.keyboards.help import build_help_keyboard
from src.keyboards.settings import build_settings_keyboard
from src.keyboards.shop import build_shop_keyboard
from src.keyboards.why import build_why_keyboard
from src.services.l3_runtime import apply_l3_turn
from src.services.runtime_sessions import (
    abort_session,
    get_session,
    get_session_by_sid8,
    has_active,
    touch_last_step,
)
from src.services.story_runtime import render_step
from src.services.ui_delivery import deliver_step_view
from src.services.theme_registry import registry
from src.states import L3, L4, L5, UX

router = Router(name="l1")
logger = logging.getLogger(__name__)

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


async def open_l1(message: Message, state: FSMContext, user_id: int | None = None) -> None:
    # MVP-правило: только private чат.
    if message.chat.type != "private":
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return
    tg_id = user_id if user_id is not None else message.from_user.id

    await state.set_state(UX.l1)
    try:
        active = has_active(tg_id)
    except Exception:
        logger.exception("Failed to load active session")
        active = False
    await message.answer(
        "🏠 Главное меню",
        reply_markup=build_l1_keyboard(active),
    )


def _is_private(message: Message) -> bool:
    return message.chat.type == "private"


async def _send_inline_screen(
    message: Message, text: str, keyboard_builder
) -> None:
    sent = await message.answer("...", reply_markup=ReplyKeyboardRemove())
    try:
        await message.bot.edit_message_text(
            text,
            chat_id=sent.chat.id,
            message_id=sent.message_id,
            reply_markup=keyboard_builder(),
        )
    except Exception:
        try:
            await message.bot.delete_message(
                chat_id=sent.chat.id,
                message_id=sent.message_id,
            )
        except Exception:
            pass
        await message.answer(text, reply_markup=keyboard_builder())


async def _send_help_screen(message: Message) -> None:
    await _send_inline_screen(
        message,
        "❓ Помощь\n\n"
        "Как начать: нажми ▶ Начать сказку и выбери тему.\n"
        "Как продолжить: ⏩ Продолжить или команда /resume.\n"
        "Почемучка: 🧠 Почемучка — задай вопрос, получишь простой ответ.\n"
        "Команды: /start /resume /status /help /shop.",
        build_help_keyboard,
    )


async def _send_shop_screen(message: Message) -> None:
    await _send_inline_screen(
        message,
        "🛒 Магазин скоро, оплаты в MVP нет.",
        build_shop_keyboard,
    )


async def _send_settings_screen(message: Message) -> None:
    await _send_inline_screen(
        message,
        "⚙ Настройки\n\nПока настроек нет, скоро появятся.",
        build_settings_keyboard,
    )


async def _handle_db_error(message: Message, state: FSMContext) -> None:
    logger.exception("DB operation failed")
    await message.answer("⚠️ База данных временно недоступна. Попробуй позже.")
    await state.set_state(UX.l1)
    await message.answer("🏠 Главное меню", reply_markup=build_l1_keyboard(False))


def _is_session_valid(session: object) -> bool:
    if not session:
        return False
    if getattr(session, "theme_id", None) is None:
        return False
    if getattr(session, "id", None) is None:
        return False
    step = getattr(session, "step", None)
    max_steps = getattr(session, "max_steps", None)
    return isinstance(step, int) and isinstance(max_steps, int)


async def _screen_label(state: FSMContext) -> str:
    state_name = await state.get_state()
    if not state_name:
        return "unknown"
    if state_name.endswith("l1"):
        return "l1"
    if state_name.endswith("l2"):
        return "l2"
    if state_name.endswith("WHY_TEXT"):
        return "why"
    if state_name.endswith("STEP"):
        return "l3"
    if state_name.endswith("HELP"):
        return "help"
    if state_name.endswith("SHOP"):
        return "shop"
    if state_name.endswith("SETTINGS"):
        return "settings"
    return "unknown"


async def do_continue(message: Message, state: FSMContext, user_id: int | None = None) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return

    tg_id = user_id if user_id is not None else message.from_user.id

    try:
        session = get_session(tg_id)
    except Exception:
        await _handle_db_error(message, state)
        return

    if not session:
        await message.answer("Нет активной сказки. Нажми ▶ Начать сказку.")
        await open_l1(message, state, user_id=tg_id)
        return

    if not _is_session_valid(session):
        try:
            abort_session(tg_id)
        except Exception:
            await _handle_db_error(message, state)
            return
        await message.answer("Сессия потерялась. Начни заново.")
        await open_l1(message, state, user_id=tg_id)
        return

    now_ts = int(time())
    if session.last_step_sent_at and now_ts - session.last_step_sent_at < 5:
        await open_l1(message, state, user_id=tg_id)
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

    step_view = render_step(session.__dict__)
    step_text = step_view.text
    sent_message = await message.answer("...", reply_markup=ReplyKeyboardRemove())
    step_message = sent_message
    try:
        await message.bot.edit_message_text(
            step_text,
            chat_id=sent_message.chat.id,
            message_id=sent_message.message_id,
            reply_markup=step_view.keyboard,
        )
    except Exception:
        try:
            await message.bot.delete_message(
                chat_id=sent_message.chat.id,
                message_id=sent_message.message_id,
            )
        except Exception:
            pass
        step_message = await message.answer(step_text, reply_markup=step_view.keyboard)
    try:
        touch_last_step(tg_id, step_message.message_id, now_ts)
    except Exception:
        await _handle_db_error(message, state)
        return
    await state.set_state(L3.STEP)


@router.message(Command("resume"))
async def on_resume(message: Message, state: FSMContext) -> None:
    await do_continue(message, state)


@router.message(Command("status"))
async def on_status(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return

    try:
        session = get_session(message.from_user.id)
    except Exception:
        await _handle_db_error(message, state)
        return
    active = session is not None
    screen = await _screen_label(state)
    lines = [f"active: {'yes' if active else 'no'}"]
    lines.append(f"screen: {screen}")
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
        try:
            abort_session(message.from_user.id)
        except Exception:
            await _handle_db_error(message, state)
            return
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
    await open_l1(callback.message, state, user_id=callback.from_user.id)
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


@router.message(L3.STEP)
@router.message(L4.HELP)
@router.message(L4.SHOP)
@router.message(L4.SETTINGS)
async def on_inline_screen_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    if await state.get_state() == L3.STEP:
        await message.answer("Сейчас жми кнопки. Если потерялся, нажми ⬅ В меню.")
        return
    await message.answer("Сейчас жми кнопки. Если потерялся, нажми ⬅ В меню.")


def _parse_l3_choice_callback(data: str) -> tuple[str, str, int] | None:
    parts = data.split(":")
    if len(parts) != 5:
        return None
    _, kind, choice_id, sid8, st2_raw = parts
    if kind != "choice" or not choice_id or not sid8:
        return None
    try:
        st2 = int(st2_raw)
    except ValueError:
        return None
    return choice_id, sid8, st2


def _parse_l3_free_text_callback(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != 4:
        return None
    _, kind, sid8, st2_raw = parts
    if kind != "free_text" or not sid8:
        return None
    try:
        st2 = int(st2_raw)
    except ValueError:
        return None
    return sid8, st2


@router.callback_query(lambda query: query.data and query.data.startswith("l3:choice:"))
async def on_l3_choice(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        await callback.answer()
        return
    payload = _parse_l3_choice_callback(callback.data)
    if not payload:
        logger.info("TG.6.4.02 invalid l3 choice payload")
        await callback.answer("Кнопка недействительна или устарела.")
        return
    choice_id, sid8, st2 = payload
    try:
        session = get_session_by_sid8(callback.from_user.id, sid8)
    except Exception:
        await _handle_db_error(callback.message, state)
        await callback.answer()
        return
    if not session or not _is_session_valid(session):
        await callback.answer("Сессия устарела. Нажми /resume.")
        return
    if session.last_step_message_id and callback.message.message_id != session.last_step_message_id:
        logger.info("TG.6.4.02 stale l3 choice (message_id)")
        await callback.answer("Кнопка устарела. Продолжай в последнем сообщении.")
        return
    if st2 < session.step:
        logger.info("TG.6.4.02 stale l3 choice (step behind)")
        await callback.answer("Кнопка устарела. Продолжай в последнем сообщении.")
        return
    if st2 > session.step:
        logger.info("TG.6.4.02 future l3 choice (step ahead)")
        await callback.answer("Этот шаг ещё не активен.")
        return
    turn = {"kind": "choice", "choice_id": choice_id}
    try:
        result = apply_l3_turn(
            tg_id=callback.from_user.id,
            sid8=sid8,
            st2=st2,
            turn=turn,
            source_message_id=callback.message.message_id,
        )
    except Exception:
        await _handle_db_error(callback.message, state)
        await callback.answer()
        return
    if result is None:
        await callback.answer("Сессия устарела. Нажми /resume.")
        return
    if result.status == "stale":
        logger.info("TG.6.4.02 stale l3 choice (tx)")
        await callback.answer("Кнопка устарела. Продолжай в последнем сообщении.")
        return
    if result.status == "duplicate":
        logger.info("TG.6.4.02 duplicate l3 choice")
    else:
        logger.info("TG.6.4.02 accepted l3 choice")
    await deliver_step_view(
        message=callback.message,
        step_view=result.step_view,
        session_id=result.session_id,
        step=result.step,
        theme_id=result.theme_id,
    )
    await state.set_state(L3.STEP)
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("l3:free_text"))
async def on_l3_free_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        await callback.answer()
        return
    payload = _parse_l3_free_text_callback(callback.data)
    if not payload:
        logger.info("TG.6.4.02 invalid l3 free_text payload")
        await callback.answer("Кнопка недействительна или устарела.")
        return
    sid8, st2 = payload
    try:
        session = get_session_by_sid8(callback.from_user.id, sid8)
    except Exception:
        await _handle_db_error(callback.message, state)
        await callback.answer()
        return
    if not session or not _is_session_valid(session):
        await callback.answer("Сессия устарела. Нажми /resume.")
        return
    if session.last_step_message_id and callback.message.message_id != session.last_step_message_id:
        logger.info("TG.6.4.02 stale l3 free_text (message_id)")
        await callback.answer("Кнопка устарела. Продолжай в последнем сообщении.")
        return
    if st2 < session.step:
        logger.info("TG.6.4.02 stale l3 free_text (step behind)")
        await callback.answer("Кнопка устарела. Продолжай в последнем сообщении.")
        return
    if st2 > session.step:
        logger.info("TG.6.4.02 future l3 free_text (step ahead)")
        await callback.answer("Этот шаг ещё не активен.")
        return
    await state.set_state(L3.FREE_TEXT)
    await state.update_data(l3_sid8=sid8, l3_st2=st2)
    await callback.message.answer(
        "Напиши свой вариант текста. Я запомню его как ход.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.answer()


@router.message(L3.FREE_TEXT)
async def on_l3_free_text_message(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    state_data = await state.get_data()
    sid8 = state_data.get("l3_sid8")
    st2 = state_data.get("l3_st2")
    if not sid8 or st2 is None:
        logger.info("TG.6.4.02 invalid l3 free_text state")
        await message.answer("Кнопка устарела. Продолжай в последнем сообщении.")
        return
    try:
        session = get_session_by_sid8(message.from_user.id, sid8)
    except Exception:
        await _handle_db_error(message, state)
        return
    if not session or not _is_session_valid(session):
        await message.answer("Сессия устарела. Нажми /resume.")
        return
    if int(st2) != session.step:
        if int(st2) < session.step:
            logger.info("TG.6.4.02 stale l3 free_text (step behind)")
            await message.answer("Кнопка устарела. Продолжай в последнем сообщении.")
            return
        logger.info("TG.6.4.02 future l3 free_text (step ahead)")
        await message.answer("Этот шаг ещё не активен.")
        return
    turn = {"kind": "free_text", "text": message.text}
    try:
        result = apply_l3_turn(
            tg_id=message.from_user.id,
            sid8=sid8,
            st2=int(st2),
            turn=turn,
            source_message_id=message.message_id,
        )
    except Exception:
        await _handle_db_error(message, state)
        return
    if result is None:
        await message.answer("Сессия устарела. Нажми /resume.")
        return
    if result.status == "stale":
        logger.info("TG.6.4.02 stale l3 free_text (tx)")
        await message.answer("Кнопка устарела. Продолжай в последнем сообщении.")
        return
    if result.status == "duplicate":
        logger.info("TG.6.4.02 duplicate l3 free_text")
    else:
        logger.info("TG.6.4.02 accepted l3 free_text")
    await deliver_step_view(
        message=message,
        step_view=result.step_view,
        session_id=result.session_id,
        step=result.step,
        theme_id=result.theme_id,
    )
    await state.set_state(L3.STEP)


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


@router.callback_query(lambda query: query.data == "go:continue")
async def on_go_continue(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    if not callback.from_user:
        await callback.answer()
        return
    await do_continue(callback.message, state, user_id=callback.from_user.id)
    await callback.answer()


@router.message(Command("start"))
async def on_start(message: Message, state: FSMContext) -> None:
    # /start = вход в "дом" бота (L1), не "начать сказку"
    await open_l1(message, state)


async def _handle_l1_text(message: Message, state: FSMContext) -> None:
    """
    UX-правило:
    - ReplyKeyboard = текст.
    - СНАЧАЛА матчимся по лейблам кнопок (включая алиасы slash-команд).
    - Если пользователь ввёл кусок slash-команды -> показываем подсказки.
    - Потом: неизвестный ввод -> подсказка + повтор L1, без смены состояния.
    """
    if not message.text:
        await message.answer("Мне нужен текст или кнопки. Остальное я не ем.")
        try:
            active = has_active(message.from_user.id)
        except Exception:
            logger.exception("Failed to load active session")
            active = False
        await message.answer("🏠 Главное меню", reply_markup=build_l1_keyboard(active))
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
                try:
                    active = has_active(message.from_user.id)
                except Exception:
                    logger.exception("Failed to load active session")
                    active = False
                await message.answer("🏠 Главное меню", reply_markup=build_l1_keyboard(active))
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
        await state.set_state(L4.SETTINGS)
        await _send_settings_screen(message)
        return

    # 2) Потом: "произвольный" неизвестный ввод
    await message.answer("Не понял. Используй кнопки меню или команды /start /help.")
    try:
        active = has_active(message.from_user.id)
    except Exception:
        logger.exception("Failed to load active session")
        active = False
    await message.answer("🏠 Главное меню", reply_markup=build_l1_keyboard(active))


@router.message(StateFilter(None))
async def l1_any_default(message: Message, state: FSMContext) -> None:
    await state.set_state(UX.l1)
    await _handle_l1_text(message, state)


@router.message(UX.l1)
async def l1_any(message: Message, state: FSMContext) -> None:
    await _handle_l1_text(message, state)
