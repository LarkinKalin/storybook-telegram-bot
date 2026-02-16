from __future__ import annotations

import asyncio
import logging
import os
from time import time

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest

from src.handlers.l2 import open_l2
from src.keyboards.l1 import L1Label, build_l1_keyboard
from src.keyboards.l3 import build_locked_keyboard
from src.keyboards.help import build_help_keyboard
from src.keyboards.settings import build_settings_keyboard
from src.keyboards.shop import build_shop_keyboard
from src.keyboards.book import build_book_offer_keyboard
from src.keyboards.why import build_why_keyboard
from src.services.l3_runtime import apply_l3_turn
from src.services.runtime_sessions import (
    abort_session,
    get_session,
    get_session_by_sid8,
    has_active,
    is_step_current,
    touch_last_step,
)
from src.services.story_runtime import ensure_engine_state, render_current_step
from src.services.ui_delivery import (
    acquire_step_event,
    content_hash,
    deliver_step_lock,
    deliver_step_view,
    _normalize_content,
)
from src.services.image_delivery import resolve_story_step_ui, schedule_image_delivery
from db.repos import ui_events, users
from src.services.content_stub import build_content_step
from db.repos import session_events
from src.services.theme_registry import registry
from src.states import L3, L4, L5, UX
from src.services.book_runtime import (
    book_offer_text,
    run_book_job,
    run_dev_layout_test,
    run_dev_rewrite_test,
    send_sample_pdf,
)
from src.services.dev_tools import (
    activate_session_for_user,
    can_use_dev_tools,
    ensure_demo_session_ready,
    fast_forward_active_session,
    fast_forward_to_final,
)

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


async def safe_callback_answer(callback: CallbackQuery, text: str | None = None, **kwargs) -> None:
    try:
        if text is not None:
            await callback.answer(text, **kwargs)
        else:
            await callback.answer(**kwargs)
    except TelegramBadRequest as exc:
        logger.warning("callback.answer skipped reason=%s", exc)




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
    add_dev = bool(message.from_user and can_use_dev_tools(message.from_user.id))
    await _send_inline_screen(
        message,
        "⚙ Настройки\n\nМожно сохранить имя ребёнка для сказок и будущей книжки.",
        lambda: build_settings_keyboard(add_dev_tools=add_dev),
    )



def _book_offer_enabled() -> bool:
    raw = os.getenv("SKAZKA_BOOK_OFFER", "1").strip().lower()
    if raw == "":
        raw = "1"
    return raw in {"1", "true", "yes", "on"}


async def _send_book_offer(message: Message) -> None:
    await message.answer(book_offer_text(), reply_markup=build_book_offer_keyboard())


def _normalize_child_name(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 32:
        value = value[:32]
    return value



async def _maybe_send_book_offer(message: Message, result) -> None:
    session_id = getattr(result, "session_id", None) if result else None
    step = getattr(result, "step", None) if result else None
    max_steps = getattr(result, "max_steps", None) if result else None
    ending_id_present = bool(getattr(result, "final_id", None)) if result else False

    if not _book_offer_enabled():
        logger.info(
            "book.offer decision reason=disabled session_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
            session_id,
            step,
            max_steps,
            ending_id_present,
            message.chat.id,
        )
        return
    if not result:
        logger.info(
            "book.offer decision reason=no_result session_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
            session_id,
            step,
            max_steps,
            ending_id_present,
            message.chat.id,
        )
        return
    if not getattr(result, "step_view", None):
        logger.info(
            "book.offer decision reason=no_step_view session_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
            session_id,
            step,
            max_steps,
            ending_id_present,
            message.chat.id,
        )
        return

    final_id = getattr(result, "final_id", None) or getattr(result.step_view, "final_id", None)
    ending_id_present = bool(final_id)
    step0 = getattr(result, "step", None)
    total_steps = getattr(result, "max_steps", None)
    finished_by_step = isinstance(step0, int) and isinstance(total_steps, int) and step0 >= total_steps - 1
    is_finished = ending_id_present or finished_by_step
    if not is_finished:
        logger.info(
            "book.offer decision reason=not_finished session_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
            session_id,
            step0,
            total_steps,
            ending_id_present,
            message.chat.id,
        )
        return

    await _send_book_offer(message)
    logger.info(
        "book.offer shown session_id=%s sid8=%s final_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
        session_id,
        getattr(result, "sid8", None),
        final_id,
        step0,
        total_steps,
        ending_id_present,
        message.chat.id,
    )



def _book_offer_enabled() -> bool:
    raw = os.getenv("SKAZKA_BOOK_OFFER", "1").strip().lower()
    if raw == "":
        raw = "1"
    return raw in {"1", "true", "yes", "on"}


async def _send_book_offer(message: Message) -> None:
    await message.answer(book_offer_text(), reply_markup=build_book_offer_keyboard())


def _normalize_child_name(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 32:
        value = value[:32]
    return value



async def _maybe_send_book_offer(message: Message, result) -> None:
    session_id = getattr(result, "session_id", None) if result else None
    step = getattr(result, "step", None) if result else None
    max_steps = getattr(result, "max_steps", None) if result else None
    ending_id_present = bool(getattr(result, "final_id", None)) if result else False

    if not _book_offer_enabled():
        logger.info(
            "book.offer decision reason=disabled session_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
            session_id,
            step,
            max_steps,
            ending_id_present,
            message.chat.id,
        )
        return
    if not result:
        logger.info(
            "book.offer decision reason=no_result session_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
            session_id,
            step,
            max_steps,
            ending_id_present,
            message.chat.id,
        )
        return
    if not getattr(result, "step_view", None):
        logger.info(
            "book.offer decision reason=no_step_view session_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
            session_id,
            step,
            max_steps,
            ending_id_present,
            message.chat.id,
        )
        return

    final_id = getattr(result, "final_id", None) or getattr(result.step_view, "final_id", None)
    ending_id_present = bool(final_id)
    step0 = getattr(result, "step", None)
    total_steps = getattr(result, "max_steps", None)
    finished_by_step = isinstance(step0, int) and isinstance(total_steps, int) and step0 >= total_steps - 1
    is_finished = ending_id_present or finished_by_step
    if not is_finished:
        logger.info(
            "book.offer decision reason=not_finished session_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
            session_id,
            step0,
            total_steps,
            ending_id_present,
            message.chat.id,
        )
        return

    await _send_book_offer(message)
    logger.info(
        "book.offer shown session_id=%s sid8=%s final_id=%s step=%s max_steps=%s ending_id_present=%s chat_id=%s",
        session_id,
        getattr(result, "sid8", None),
        final_id,
        step0,
        total_steps,
        ending_id_present,
        message.chat.id,
    )



def _book_offer_enabled() -> bool:
    raw = os.getenv("SKAZKA_BOOK_OFFER", "1").strip().lower()
    if raw == "":
        raw = "1"
    return raw in {"1", "true", "yes", "on"}


async def _send_book_offer(message: Message) -> None:
    await message.answer(book_offer_text(), reply_markup=build_book_offer_keyboard())


def _normalize_child_name(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 32:
        value = value[:32]
    return value



async def _maybe_send_book_offer(message: Message, result) -> None:
    if not _book_offer_enabled():
        logger.info("book.offer skip reason=disabled chat_id=%s", message.chat.id)
        return
    if not result:
        logger.info("book.offer skip reason=no_result chat_id=%s", message.chat.id)
        return
    if not getattr(result, "step_view", None):
        logger.info("book.offer skip reason=no_step_view chat_id=%s", message.chat.id)
        return
    final_id = getattr(result, "final_id", None) or getattr(result.step_view, "final_id", None)
    if not final_id:
        logger.info("book.offer skip reason=no_final chat_id=%s", message.chat.id)
        return
    await _send_book_offer(message)
    logger.info(
        "book.offer shown session_id=%s sid8=%s final_id=%s enabled=true chat_id=%s",
        getattr(result, "session_id", None),
        getattr(result, "sid8", None),
        final_id,
        message.chat.id,
    )



def _book_offer_enabled() -> bool:
    raw = os.getenv("SKAZKA_BOOK_OFFER", "1").strip().lower()
    if raw == "":
        raw = "1"
    return raw in {"1", "true", "yes", "on"}


async def _send_book_offer(message: Message) -> None:
    await message.answer(book_offer_text(), reply_markup=build_book_offer_keyboard())


def _normalize_child_name(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 32:
        value = value[:32]
    return value



async def _maybe_send_book_offer(message: Message, result) -> None:
    if not _book_offer_enabled():
        logger.info("book.offer skip reason=disabled chat_id=%s", message.chat.id)
        return
    if not result:
        logger.info("book.offer skip reason=no_result chat_id=%s", message.chat.id)
        return
    if not getattr(result, "step_view", None):
        logger.info("book.offer skip reason=no_step_view chat_id=%s", message.chat.id)
        return
    final_id = getattr(result, "final_id", None) or getattr(result.step_view, "final_id", None)
    if not final_id:
        logger.info("book.offer skip reason=no_final chat_id=%s", message.chat.id)
        return
    await _send_book_offer(message)
    logger.info(
        "book.offer sent session_id=%s sid8=%s final_id=%s enabled=true chat_id=%s",
        getattr(result, "session_id", None),
        getattr(result, "sid8", None),
        final_id,
        message.chat.id,
<<<<<<< ours
    )



def _book_offer_enabled() -> bool:
    raw = os.getenv("SKAZKA_BOOK_OFFER", "1").strip().lower()
    if raw == "":
        raw = "1"
    return raw in {"1", "true", "yes", "on"}


async def _send_book_offer(message: Message) -> None:
    await message.answer(book_offer_text(), reply_markup=build_book_offer_keyboard())


def _normalize_child_name(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 32:
        value = value[:32]
    return value



async def _maybe_send_book_offer(message: Message, result) -> None:
    if not _book_offer_enabled():
        return
    if not result or not getattr(result, "step_view", None):
        return
    if not (getattr(result, "final_id", None) or getattr(result.step_view, "final_id", None)):
        return
    await _send_book_offer(message)
    logger.info(
        "book.offer shown session_id=%s sid8=%s enabled=true chat_id=%s",
        getattr(result, "session_id", None),
        getattr(result, "sid8", None),
        message.chat.id,
    )



def _book_offer_enabled() -> bool:
    raw = os.getenv("SKAZKA_BOOK_OFFER", "1").strip().lower()
    if raw == "":
        raw = "1"
    return raw in {"1", "true", "yes", "on"}


async def _send_book_offer(message: Message) -> None:
    await message.answer(book_offer_text(), reply_markup=build_book_offer_keyboard())


def _normalize_child_name(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 32:
        value = value[:32]
    return value



async def _maybe_send_book_offer(message: Message, result) -> None:
    if not _book_offer_enabled():
        return
    if not result or not getattr(result, "step_view", None):
        return
    if not (getattr(result, "final_id", None) or getattr(result.step_view, "final_id", None)):
        return
    await _send_book_offer(message)
    logger.info(
        "book.offer shown session_id=%s sid8=%s enabled=true chat_id=%s",
        getattr(result, "session_id", None),
        getattr(result, "sid8", None),
        message.chat.id,
=======
>>>>>>> theirs
    )



def _book_offer_enabled() -> bool:
    raw = os.getenv("SKAZKA_BOOK_OFFER", "1").strip().lower()
    if raw == "":
        raw = "1"
    return raw in {"1", "true", "yes", "on"}


async def _send_book_offer(message: Message) -> None:
    await message.answer(book_offer_text(), reply_markup=build_book_offer_keyboard())


def _normalize_child_name(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 32:
        value = value[:32]
    return value



async def _maybe_send_book_offer(message: Message, result) -> None:
    if not _book_offer_enabled():
        return
    if not result or not getattr(result, "step_view", None):
        return
    if not (getattr(result, "final_id", None) or getattr(result.step_view, "final_id", None)):
        return
    await _send_book_offer(message)
    logger.info(
        "book.offer shown session_id=%s sid8=%s enabled=true chat_id=%s",
        getattr(result, "session_id", None),
        getattr(result, "sid8", None),
        message.chat.id,
    )



def _book_offer_enabled() -> bool:
    raw = os.getenv("SKAZKA_BOOK_OFFER", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


async def _send_book_offer(message: Message) -> None:
    await message.answer(book_offer_text(), reply_markup=build_book_offer_keyboard())


def _normalize_child_name(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 32:
        value = value[:32]
    return value



async def _maybe_send_book_offer(message: Message, result) -> None:
    if not _book_offer_enabled():
        return
    if not result or not getattr(result, "step_view", None):
        return
    if not (getattr(result, "final_id", None) or getattr(result.step_view, "final_id", None)):
        return
    await _send_book_offer(message)
    logger.info("book.offer shown chat_id=%s", message.chat.id)


async def _handle_db_error(
    message: Message,
    state: FSMContext,
    *,
    session_id: int | None = None,
    step: int | None = None,
    step0: int | None = None,
    req_id: str | None = None,
    exc: Exception | None = None,
) -> None:
    reason = _db_error_reason(exc)
    if session_id is not None or step is not None:
        _log_l3_step(
            "invalid",
            reason,
            session_id=session_id,
            step=step,
            step0=step0,
            req_id=req_id,
        )
    if exc is not None:
        logger.exception(
            "db_unavailable reason=%s exc_class=%s",
            reason,
            type(exc).__name__,
        )
    else:
        logger.error("db_unavailable reason=%s", reason)
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


def _log_l3_step(
    outcome: str,
    reason: str,
    *,
    session_id: int | None,
    step: int | None,
    step0: int | None,
    req_id: str | None,
) -> None:
    session_value = session_id if session_id is not None else "unknown"
    step_value = step if step is not None else "unknown"
    step0_value = step0 if step0 is not None else "unknown"
    req_value = req_id if req_id is not None else "unknown"
    logger.info(
        "event=l3_step outcome=%s reason=%s session_id=%s step=%s step0=%s req_id=%s",
        outcome,
        reason,
        session_value,
        step_value,
        step0_value,
        req_value,
    )


def _req_id_from_update(message: Message | None, callback: CallbackQuery | None) -> str | None:
    if callback and getattr(callback, "id", None):
        return str(callback.id)
    if message and getattr(message, "message_id", None):
        return str(message.message_id)
    return None


def _db_error_reason(exc: Exception | None) -> str:
    if exc is None:
        return "db_unavailable"
    if isinstance(exc, UnboundLocalError):
        return "code_unbound_local_error"
    msg = str(exc).lower()
    if "does not exist" in msg or "undefined table" in msg:
        return "db_schema_missing"
    if "could not connect" in msg or "connection refused" in msg or "connection" in msg:
        return "db_connect_failed"
    return "db_tx_failed"


async def _deliver_current_step(
    message: Message,
    state: FSMContext,
    session: object,
) -> None:
    step_view = render_current_step(session.__dict__, req_id=_req_id_from_update(message, None))
    await deliver_step_view(
        message=message,
        step_view=step_view,
        session_id=session.id,
        step=session.step,
        theme_id=session.theme_id,
        total_steps=session.max_steps,
    )
    await state.set_state(L3.STEP)


async def _continue_current(
    message: Message,
    state: FSMContext,
    session: object,
    *,
    source: str,
) -> None:
    now_ts = int(time())
    if (
        source == "resume_cmd"
        and getattr(session, "last_step_message_id", None)
        and getattr(session, "last_step_sent_at", None)
        and now_ts - session.last_step_sent_at <= 5
    ):
        logger.info(
            "TG.6.4.10 continue source=%s outcome=duplicate_window session_id=%s step=%s",
            source,
            session.id,
            session.step,
        )
        return
    kind = "resume_shown" if source == "resume_cmd" else "continue_shown"
    dedup_hash = content_hash(theme_id=None, text=f"{kind}:{session.step}")
    acquire = acquire_step_event(
        session_id=session.id,
        step=session.step,
        kind=kind,
        content_hash_value=dedup_hash,
    )
    if acquire.decision != "show" or acquire.event_id is None:
        logger.info(
            "TG.6.4.10 continue source=%s outcome=duplicate_window session_id=%s step=%s",
            source,
            session.id,
            session.step,
        )
        return
    step_view = render_current_step(session.__dict__, req_id=_req_id_from_update(message, None))
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
        touch_last_step(session.tg_id, step_message.message_id, now_ts)
    except Exception as exc:
        await _handle_db_error(message, state, exc=exc)
        return
    try:
        ui_events.mark_shown(acquire.event_id, step_message_id=step_message.message_id)
    except Exception:
        pass
    scene_brief = step_view.image_prompt
    if not scene_brief:
        normalized = _normalize_content(step_text)
        scene_brief = normalized[:200] if normalized else None
    # Engine step is zero-based; UI/story step index is step0 + 1.
    story_step_ui = resolve_story_step_ui(session.step)
    step_ui = story_step_ui
    logger.warning(
        "TG.7.4.01 entrypoint l1_continue schedule_image_delivery session_id=%s step_ui=%s story_step_ui=%s",
        session.id,
        step_ui,
        story_step_ui,
    )
    try:
        schedule_image_delivery(
            bot=message.bot,
            chat_id=step_message.chat.id,
            step_message_id=step_message.message_id,
            session_id=session.id,
            engine_step=session.step,
            step_ui=step_ui,
            story_step_ui=story_step_ui,
            total_steps=session.max_steps,
            prompt=step_text,
            theme_id=session.theme_id,
            image_scene_brief=scene_brief,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "TG.7.4.01 image_outcome outcome=error reason=%s session_id=%s step_ui=%s",
            str(exc),
            session.id,
            step_ui,
            exc_info=exc,
        )
    logger.info(
        "TG.6.4.10 continue source=%s outcome=shown session_id=%s step=%s",
        source,
        session.id,
        session.step,
    )
    await state.set_state(L3.STEP)


async def do_continue(message: Message, state: FSMContext, user_id: int | None = None) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return

    tg_id = user_id if user_id is not None else message.from_user.id

    try:
        session = get_session(tg_id)
    except Exception as exc:
        await _handle_db_error(message, state, exc=exc)
        return

    if not session:
        logger.info("TG.6.4.10 continue source=menu outcome=no_active tg_id=%s", tg_id)
        await message.answer("Нет активной сказки. Нажми ▶ Начать сказку.")
        await open_l1(message, state, user_id=tg_id)
        return

    if not _is_session_valid(session):
        try:
            abort_session(tg_id)
        except Exception as exc:
            await _handle_db_error(message, state, exc=exc)
            return
        await message.answer("Сессия потерялась. Начни заново.")
        await open_l1(message, state, user_id=tg_id)
        return

    await _continue_current(message, state, session, source="menu")


@router.message(Command("resume"), StateFilter("*"))
async def on_resume(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return
    try:
        session = get_session(message.from_user.id)
    except Exception as exc:
        await _handle_db_error(message, state, exc=exc)
        return
    if not session or not _is_session_valid(session):
        logger.info(
            "TG.6.4.10 continue source=resume_cmd outcome=no_active tg_id=%s",
            message.from_user.id,
        )
        await message.answer("Сессия устарела. Нажми /resume.")
        return
    await _continue_current(message, state, session, source="resume_cmd")


@router.message(Command("status"), StateFilter("*"))
async def on_status(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return

    try:
        session = get_session(message.from_user.id)
    except Exception as exc:
        await _handle_db_error(message, state, exc=exc)
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
        except Exception as exc:
            await _handle_db_error(message, state, exc=exc)
            return
    await message.answer("\n".join(lines))


@router.message(Command("help"), StateFilter("*"))
async def on_help(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return
    logger.info("TG.6.4.10 cmd=/help outcome=help_shown")
    await state.set_state(L4.HELP)
    await _send_help_screen(message)


@router.message(Command("settings"), StateFilter("*"))
async def on_settings(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return
    logger.info("TG.6.4.10 cmd=/settings outcome=settings_shown")
    await state.set_state(L4.SETTINGS)
    await _send_settings_screen(message)






@router.message(Command("dev_id"), StateFilter("*"))
async def on_dev_id(message: Message) -> None:
    if not message.from_user:
        return
    if not can_use_dev_tools(message.from_user.id):
        await message.answer("Dev tools недоступны.")
        return
    await message.answer(f"Ваш tg_id: {message.from_user.id}")


@router.message(Command("dev_finish"), StateFilter("*"))
async def on_dev_finish(message: Message) -> None:
    if not message.from_user:
        return
    if not can_use_dev_tools(message.from_user.id):
        await message.answer("Dev tools недоступны.")
        return
    ok, msg = fast_forward_to_final(message.from_user.id)
    await message.answer(msg)
    if ok:
        await _send_book_offer(message)
        logger.info("book.offer shown chat_id=%s source=dev_finish", message.chat.id)




@router.message(Command("dev_book_offer"), StateFilter("*"))
async def on_dev_book_offer(message: Message) -> None:
    if not message.from_user:
        return
    if not can_use_dev_tools(message.from_user.id):
        await message.answer("Dev tools недоступны.")
        return
    await _send_book_offer(message)
    logger.info("book.offer shown chat_id=%s source=dev_book_offer", message.chat.id)


@router.message(Command("dev_book"), StateFilter("*"))
@router.message(Command("dev_book_gen"), StateFilter("*"))
async def on_dev_book_gen(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    if not can_use_dev_tools(message.from_user.id):
        await message.answer("Dev tools недоступны.")
        return
    try:
        session = get_session(message.from_user.id)
    except Exception as exc:
        await _handle_db_error(message, state, exc=exc)
        return
    if not session:
        await message.answer("Нет активной сессии. Сначала нажми 🧪 Тест книги или /dev_book_offer")
        return
    await message.answer("⏳ Запускаю dev-генерацию книги…")
    await run_book_job(message, session.__dict__, theme_title=session.theme_id)


@router.message(Command("dev_ff"), StateFilter("*"))
async def on_dev_ff(message: Message) -> None:
    if not message.from_user:
        return
    if not can_use_dev_tools(message.from_user.id):
        await message.answer("Dev tools недоступны.")
        return
    to_step = 7
    final_mode = False
    if message.text:
        parts = message.text.strip().split()
        if len(parts) >= 2:
            if parts[1].strip().lower() == "final":
                final_mode = True
            else:
                try:
                    to_step = int(parts[1])
                except ValueError:
                    await message.answer("Использование: /dev_ff 7 или /dev_ff final")
                    return
    if final_mode:
        ok, msg = fast_forward_to_final(message.from_user.id)
    else:
        ok, msg = fast_forward_active_session(message.from_user.id, to_step=to_step)
    await message.answer(msg)
    if ok and final_mode:
        await _send_book_offer(message)
        logger.info("book.offer shown chat_id=%s source=dev_ff_final", message.chat.id)


@router.message(Command("dev_use_session"), StateFilter("*"))
async def on_dev_use_session(message: Message) -> None:
    if not message.from_user:
        return
    if not can_use_dev_tools(message.from_user.id):
        await message.answer("Dev tools недоступны.")
        return
    sid8 = ""
    if message.text:
        parts = message.text.strip().split()
        if len(parts) >= 2:
            sid8 = parts[1].strip()
    if not sid8:
        await message.answer("Использование: /dev_use_session <sid8>")
        return
    session = activate_session_for_user(message.from_user.id, sid8)
    if not session:
        await message.answer("Сессия не найдена.")
        return
    await message.answer(f"Сессия подключена: {session.sid8}, текущий шаг {session.step + 1}.")

@router.message(Command("dev_seed"), StateFilter("*"))
async def on_dev_seed(message: Message) -> None:
    if not message.from_user:
        return
    if not can_use_dev_tools(message.from_user.id):
        await message.answer("Dev tools недоступны.")
        return
    session = ensure_demo_session_ready(message.from_user.id)
    await message.answer(f"Demo session готова: {session.sid8}, шаг {session.step + 1}.")


@router.message(Command("menu"), StateFilter("*"))
async def on_menu(message: Message, state: FSMContext) -> None:
    await open_l1(message, state)


@router.message(Command("shop"), StateFilter("*"))
async def on_shop(message: Message, state: FSMContext) -> None:
    if not _is_private(message):
        await message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        return
    await state.set_state(L4.SHOP)
    await _send_shop_screen(message)


@router.callback_query(lambda query: query.data == "go:l1")
async def on_go_l1(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await open_l1(callback.message, state, user_id=callback.from_user.id)
    await safe_callback_answer(callback)


@router.callback_query(lambda query: query.data == "go:start")
async def on_go_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await safe_callback_answer(callback)
        return
    await open_l2(callback.message, state)
    await safe_callback_answer(callback)


@router.callback_query(lambda query: query.data == "go:help")
async def on_go_help(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await safe_callback_answer(callback)
        return
    if callback.message.chat.type != "private":
        await callback.message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        await safe_callback_answer(callback)
        return
    await state.set_state(L4.HELP)
    await _send_help_screen(callback.message)
    await safe_callback_answer(callback)



@router.callback_query(lambda query: query.data == "settings:child_name")
async def on_settings_child_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        await safe_callback_answer(callback)
        return
    await state.set_state(L4.SETTINGS_CHILD_NAME)
    await callback.message.answer(
        "Введите имя ребёнка (1..32 символа).\n"
        "Отправьте пустое сообщение или '-' чтобы сбросить имя."
    )
    await safe_callback_answer(callback)


@router.message(L4.SETTINGS_CHILD_NAME)
async def on_settings_child_name_message(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    raw = (message.text or "").strip()
    normalized = None if raw in {"-", "—"} else _normalize_child_name(raw)
    if raw and normalized is None and raw not in {"-", "—"}:
        await message.answer("Имя должно быть от 1 до 32 символов.")
        return
    try:
        user = users.get_or_create_by_tg_id(message.from_user.id)
        users.update_child_name(int(user["id"]), normalized)
    except Exception as exc:
        await _handle_db_error(message, state, exc=exc)
        return
    await state.set_state(L4.SETTINGS)
    if normalized:
        await message.answer(f"Сохранил: {normalized}")
    else:
        await message.answer("Имя ребёнка сброшено.")
    await _send_settings_screen(message)


@router.callback_query(lambda query: query.data == "dev:book_layout_test")
async def on_dev_book_layout_test(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "Готовлю PDF-верстку…")
    if not callback.message or not callback.from_user:
        return
    if not can_use_dev_tools(callback.from_user.id):
        await callback.message.answer("Dev tools недоступны.")
        return
    try:
        session = ensure_demo_session_ready(callback.from_user.id)
        await run_dev_layout_test(callback.message, session.id)
    except Exception as exc:
        logger.exception("dev.book_layout_test error", exc_info=exc)
        await callback.message.answer("Не вышло собрать тестовый PDF.")


@router.callback_query(lambda query: query.data == "dev:book_rewrite_test")
async def on_dev_book_rewrite_test(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "Запускаю тест rewrite…")
    if not callback.message or not callback.from_user:
        return
    if not can_use_dev_tools(callback.from_user.id):
        await callback.message.answer("Dev tools недоступны.")
        return
    try:
        session = ensure_demo_session_ready(callback.from_user.id)
        await run_dev_rewrite_test(callback.message, session.__dict__, theme_title="Demo Book")
    except Exception as exc:
        logger.exception("dev.book_rewrite_test error", exc_info=exc)
        await callback.message.answer("Не вышло сделать rewrite-тест.")


@router.callback_query(lambda query: query.data == "dev:book_test")
async def on_dev_book_test(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "Генерирую PDF…")
    if not callback.message or not callback.from_user:
        return
    if not can_use_dev_tools(callback.from_user.id):
        await callback.message.answer("Dev tools недоступны.")
        return

    async def _run() -> None:
        try:
            session = get_session(callback.from_user.id)
            if not session:
                await callback.message.answer("Нет активной сессии. Сначала подключи /dev_use_session <sid8>.")
                return
            # If active session is not finalized yet — fast-finish first.
            if not session.ending_id:
                ok, msg = fast_forward_to_final(callback.from_user.id)
                await callback.message.answer(msg)
                if not ok:
                    return
            refreshed = get_session(callback.from_user.id)
            if not refreshed:
                await callback.message.answer("Не удалось получить активную сессию после dev_finish.")
                return
            await run_book_job(callback.message, refreshed.__dict__, theme_title=refreshed.theme_id)
        except Exception as exc:
            logger.exception("dev.book_test error", exc_info=exc)
            await callback.message.answer("Не вышло собрать тестовую книгу. Попробуй ещё раз.")

    asyncio.create_task(_run())


@router.callback_query(lambda query: query.data == "book:sample")
async def on_book_sample(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "Отправляю образец…")
    if not callback.message:
        return
    await send_sample_pdf(callback.message)


@router.callback_query(lambda query: query.data == "book:buy")
async def on_book_buy(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback, "Собираю книгу…")
    if not callback.message or not callback.from_user:
        return
    try:
        session = get_session(callback.from_user.id)
    except Exception as exc:
        await _handle_db_error(callback.message, state, exc=exc)
        return
    if not session:
        await callback.message.answer("Нет активной или завершённой сессии для сборки книги.")
        return
    await callback.message.answer("Запускаю сборку книги. Это займёт немного времени ⏳")
    await run_book_job(callback.message, session.__dict__, theme_title=session.theme_id)


@router.message(L3.STEP)
@router.message(L4.HELP)
@router.message(L4.SHOP)
@router.message(L4.SETTINGS)
async def on_inline_screen_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    if message.text.strip().startswith("/"):
        logger.info("TG.6.4.10 cmd=%s outcome=unknown_command_menu", message.text.strip())
        await open_l1(message, state, user_id=message.from_user.id)
        return
    if await state.get_state() == L3.STEP:
        _log_l3_step(
            "invalid",
            "text_not_expected",
            session_id=None,
            step=None,
            step0=None,
            req_id=_req_id_from_update(message, None),
        )
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


def _parse_locked_callback(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) < 3:
        return None
    if parts[0] != "locked":
        return None
    try:
        step = int(parts[2])
    except ValueError:
        return None
    return parts[1], step


async def _clear_l3_free_text_state(state: FSMContext) -> None:
    await state.update_data(l3_sid8=None, l3_st2=None)


def _locked_rows_from_markup(markup: object | None) -> list[list[dict]]:
    if not markup or not getattr(markup, "inline_keyboard", None):
        return []
    rows: list[list[dict]] = []
    for row in markup.inline_keyboard:
        locked_row: list[dict] = []
        for button in row:
            choice_id = "locked"
            if button.callback_data:
                parts = button.callback_data.split(":")
                if len(parts) >= 3 and parts[0] == "l3" and parts[1] == "choice":
                    choice_id = parts[2]
                elif button.callback_data.startswith("l3:free_text"):
                    choice_id = "free_text"
                elif button.callback_data == "go:l1":
                    choice_id = "menu"
            locked_row.append({"text": button.text, "choice_id": choice_id})
        rows.append(locked_row)
    return rows


def _locked_rows_from_content(session: object, step: int) -> list[list[dict]]:
    state = ensure_engine_state(session.__dict__)
    if int(state.get("step0", 0)) != int(step):
        return []
    content = build_content_step(session.theme_id, state["step0"], state)
    rows: list[list[dict]] = []
    if content.get("choices"):
        rows.append(
            [
                {"text": choice["label"], "choice_id": choice["choice_id"]}
                for choice in content["choices"]
            ]
        )
    if state.get("free_text_allowed_after"):
        rows.append([{"text": "✍️ Свой вариант", "choice_id": "free_text"}])
    rows.append([{"text": "⬅ В меню", "choice_id": "menu"}])
    return rows


@router.callback_query(lambda query: query.data and query.data.startswith("l3:choice:"))
async def on_l3_choice(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    if not callback.message or not callback.from_user:
        return
    if await state.get_state() == L3.FREE_TEXT:
        await _clear_l3_free_text_state(state)
    payload = _parse_l3_choice_callback(callback.data)
    if not payload:
        _log_l3_step(
            "invalid",
            "invalid_payload",
            session_id=None,
            step=None,
            step0=None,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Кнопка недействительна или устарела.")
        return
    choice_id, sid8, st2 = payload
    try:
        session = get_session_by_sid8(callback.from_user.id, sid8)
    except Exception as exc:
        await _handle_db_error(
            callback.message,
            state,
            session_id=None,
            step=st2,
            step0=None,
            req_id=_req_id_from_update(callback.message, callback),
            exc=exc,
        )
        await safe_callback_answer(callback)
        return
    if not session or not _is_session_valid(session):
        _log_l3_step(
            "stale",
            "session_missing",
            session_id=getattr(session, "id", None),
            step=getattr(session, "step", None),
            step0=getattr(session, "step", None),
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Сессия устарела. Нажми /resume.")
        return
    if session.last_step_message_id and callback.message.message_id != session.last_step_message_id:
        _log_l3_step(
            "stale",
            "message_id_mismatch",
            session_id=session.id,
            step=session.step,
            step0=session.step,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        await _deliver_current_step(callback.message, state, session)
        return
    if st2 < session.step:
        _log_l3_step(
            "stale",
            "step_behind",
            session_id=session.id,
            step=session.step,
            step0=session.step,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        await _deliver_current_step(callback.message, state, session)
        return
    if st2 > session.step:
        _log_l3_step(
            "stale",
            "step_ahead",
            session_id=session.id,
            step=session.step,
            step0=session.step,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        await _deliver_current_step(callback.message, state, session)
        return
    state_snapshot = ensure_engine_state(session.__dict__)
    content_snapshot = build_content_step(session.theme_id, state_snapshot["step0"], state_snapshot)
    choice_label = None
    for choice in content_snapshot.get("choices", []):
        if choice["choice_id"] == choice_id:
            choice_label = choice["label"]
            break
    turn = {"kind": "choice", "choice_id": choice_id}
    try:
        result = apply_l3_turn(
            tg_id=callback.from_user.id,
            sid8=sid8,
            st2=st2,
            turn=turn,
            source_message_id=callback.message.message_id,
            req_id=_req_id_from_update(callback.message, callback),
        )
    except Exception as exc:
        await _handle_db_error(
            callback.message,
            state,
            session_id=session.id,
            step=st2,
            step0=st2,
            req_id=_req_id_from_update(callback.message, callback),
            exc=exc,
        )
        await safe_callback_answer(callback)
        return
    if result is None:
        _log_l3_step(
            "stale",
            "session_missing",
            session_id=None,
            step=st2,
            step0=st2,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Сессия устарела. Нажми /resume.")
        return
    if result.status == "invalid":
        _log_l3_step(
            "invalid",
            "invalid_turn",
            session_id=result.session_id or None,
            step=st2,
            step0=st2,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход отклонён. Попробуй ещё раз.")
        return
    if result.status == "stale":
        _log_l3_step(
            "stale",
            "tx_stale",
            session_id=result.session_id,
            step=result.step,
            step0=result.step,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        await _deliver_current_step(callback.message, state, session)
        return
    if result.status == "duplicate":
        _log_l3_step(
            "duplicate",
            "duplicate_insert",
            session_id=result.session_id,
            step=st2,
            step0=st2,
            req_id=_req_id_from_update(callback.message, callback),
        )
    else:
        _log_l3_step(
            "accepted",
            "applied",
            session_id=result.session_id,
            step=st2,
            step0=st2,
            req_id=_req_id_from_update(callback.message, callback),
        )
    locked_rows = _locked_rows_from_markup(callback.message.reply_markup)
    if not locked_rows:
        locked_rows = _locked_rows_from_content(session, st2)
    locked_keyboard = (
        build_locked_keyboard(locked_rows, sid8, st2) if locked_rows else None
    )
    await deliver_step_lock(
        bot=callback.message.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        session_id=result.session_id,
        step=st2,
        reply_markup=locked_keyboard,
    )
    logger.info("TG.6.4.07 keyboard=cleared msg_id=%s", callback.message.message_id)
    if result.status == "duplicate":
        await deliver_step_view(
            message=callback.message,
            step_view=result.step_view,
            session_id=result.session_id,
            step=result.step,
            theme_id=result.theme_id,
            total_steps=session.max_steps,
        )
        await _maybe_send_book_offer(callback.message, result)
        await state.set_state(L3.STEP)
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        return
    if choice_label:
        await callback.message.answer(f"Твой выбор: {choice_label}")
    await deliver_step_view(
        message=callback.message,
        step_view=result.step_view,
        session_id=result.session_id,
        step=result.step,
        theme_id=result.theme_id,
        total_steps=session.max_steps,
    )
    await _maybe_send_book_offer(callback.message, result)
    await state.set_state(L3.STEP)
    await _clear_l3_free_text_state(state)
    await safe_callback_answer(callback)


@router.callback_query(lambda query: query.data and query.data.startswith("locked:"))
async def on_locked_step(callback: CallbackQuery, state: FSMContext) -> None:
    session_id = None
    step = None
    payload = _parse_locked_callback(callback.data)
    if payload and callback.from_user:
        sid8, step = payload
        try:
            session = get_session_by_sid8(callback.from_user.id, sid8)
            if session:
                session_id = session.id
        except Exception:
            session_id = None
    _log_l3_step(
        "duplicate",
        "locked_button",
        session_id=session_id,
        step=step,
        step0=step,
        req_id=_req_id_from_update(callback.message, callback),
    )
    if callback.message and payload and session_id and callback.from_user:
        try:
            session = get_session_by_sid8(callback.from_user.id, payload[0])
        except Exception:
            session = None
        if session:
            await _deliver_current_step(callback.message, state, session)
    await safe_callback_answer(callback, "Этот шаг уже сыгран")


@router.callback_query(lambda query: query.data and query.data.startswith("l3:free_text"))
async def on_l3_free_text(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    if not callback.message or not callback.from_user:
        return
    payload = _parse_l3_free_text_callback(callback.data)
    if not payload:
        _log_l3_step(
            "invalid",
            "invalid_payload",
            session_id=None,
            step=None,
            step0=None,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Кнопка недействительна или устарела.")
        return
    sid8, st2 = payload
    try:
        session = get_session_by_sid8(callback.from_user.id, sid8)
    except Exception as exc:
        await _handle_db_error(
            callback.message,
            state,
            session_id=None,
            step=st2,
            step0=None,
            req_id=_req_id_from_update(callback.message, callback),
            exc=exc,
        )
        await safe_callback_answer(callback)
        return
    if not session or not _is_session_valid(session):
        _log_l3_step(
            "stale",
            "session_missing",
            session_id=getattr(session, "id", None),
            step=getattr(session, "step", None),
            step0=getattr(session, "step", None),
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Сессия устарела. Нажми /resume.")
        return
    if session.last_step_message_id and callback.message.message_id != session.last_step_message_id:
        _log_l3_step(
            "stale",
            "message_id_mismatch",
            session_id=session.id,
            step=session.step,
            step0=session.step,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        await _deliver_current_step(callback.message, state, session)
        return
    if st2 < session.step:
        _log_l3_step(
            "stale",
            "step_behind",
            session_id=session.id,
            step=session.step,
            step0=session.step,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        await _deliver_current_step(callback.message, state, session)
        return
    if st2 > session.step:
        _log_l3_step(
            "stale",
            "step_ahead",
            session_id=session.id,
            step=session.step,
            step0=session.step,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        await _deliver_current_step(callback.message, state, session)
        return
    if not is_step_current(callback.from_user.id, sid8, st2):
        _log_l3_step(
            "stale",
            "step_check_failed",
            session_id=session.id,
            step=session.step,
            step0=session.step,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Ход уже принят. Сообщение устарело.")
        await _deliver_current_step(callback.message, state, session)
        return
    if session_events.exists_for_step(session.id, st2):
        _log_l3_step(
            "duplicate",
            "step_already_played",
            session_id=session.id,
            step=st2,
            step0=st2,
            req_id=_req_id_from_update(callback.message, callback),
        )
        await safe_callback_answer(callback, "Этот шаг уже сыгран")
        await _deliver_current_step(callback.message, state, session)
        return
    await state.set_state(L3.FREE_TEXT)
    await state.update_data(l3_sid8=sid8, l3_st2=st2)
    await callback.message.answer(
        "Напиши свой вариант текста. Я запомню его как ход.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await safe_callback_answer(callback)


@router.message(L3.FREE_TEXT)
async def on_l3_free_text_message(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    state_data = await state.get_data()
    sid8 = state_data.get("l3_sid8")
    st2 = state_data.get("l3_st2")
    if not sid8 or st2 is None:
        _log_l3_step(
            "invalid",
            "text_not_expected",
            session_id=None,
            step=None,
            step0=None,
            req_id=_req_id_from_update(message, None),
        )
        return
    try:
        session = get_session_by_sid8(message.from_user.id, sid8)
    except Exception as exc:
        await _handle_db_error(
            message,
            state,
            session_id=None,
            step=int(st2),
            step0=None,
            req_id=_req_id_from_update(message, None),
            exc=exc,
        )
        return
    if not session or not _is_session_valid(session):
        _log_l3_step(
            "stale",
            "session_missing",
            session_id=getattr(session, "id", None),
            step=getattr(session, "step", None),
            step0=getattr(session, "step", None),
            req_id=_req_id_from_update(message, None),
        )
        await message.answer("Сессия устарела. Нажми /resume.")
        return
    if int(st2) != session.step:
        if int(st2) < session.step:
            _log_l3_step(
                "stale",
                "step_mismatch",
                session_id=session.id,
                step=session.step,
                step0=session.step,
                req_id=_req_id_from_update(message, None),
            )
            await _clear_l3_free_text_state(state)
            await _deliver_current_step(message, state, session)
            return
        _log_l3_step(
            "stale",
            "step_mismatch",
            session_id=session.id,
            step=session.step,
            step0=session.step,
            req_id=_req_id_from_update(message, None),
        )
        await _clear_l3_free_text_state(state)
        await _deliver_current_step(message, state, session)
        return
    turn = {"kind": "free_text", "text": message.text}
    try:
        result = apply_l3_turn(
            tg_id=message.from_user.id,
            sid8=sid8,
            st2=int(st2),
            turn=turn,
            source_message_id=message.message_id,
            req_id=_req_id_from_update(message, None),
        )
    except Exception as exc:
        await _handle_db_error(
            message,
            state,
            session_id=session.id,
            step=int(st2),
            step0=int(st2),
            req_id=_req_id_from_update(message, None),
            exc=exc,
        )
        return
    if result is None:
        _log_l3_step(
            "stale",
            "session_missing",
            session_id=None,
            step=st2,
            step0=st2,
            req_id=_req_id_from_update(message, None),
        )
        await message.answer("Сессия устарела. Нажми /resume.")
        return
    if result.status == "invalid":
        _log_l3_step(
            "invalid",
            "invalid_turn",
            session_id=result.session_id or None,
            step=int(st2),
            step0=int(st2),
            req_id=_req_id_from_update(message, None),
        )
        await message.answer("Ход отклонён. Попробуй ещё раз.")
        await _maybe_send_book_offer(message, result)
        await _clear_l3_free_text_state(state)
        return
    if result.status == "stale":
        _log_l3_step(
            "stale",
            "tx_stale",
            session_id=result.session_id,
            step=result.step,
            step0=result.step,
            req_id=_req_id_from_update(message, None),
        )
        await _clear_l3_free_text_state(state)
        await _deliver_current_step(message, state, session)
        return
    if result.status == "duplicate":
        _log_l3_step(
            "duplicate",
            "duplicate_insert",
            session_id=result.session_id,
            step=int(st2),
            step0=int(st2),
            req_id=_req_id_from_update(message, None),
        )
    else:
        _log_l3_step(
            "accepted",
            "applied",
            session_id=result.session_id,
            step=int(st2),
            step0=int(st2),
            req_id=_req_id_from_update(message, None),
        )
    if session.last_step_message_id:
        locked_rows = _locked_rows_from_content(session, int(st2))
        locked_keyboard = (
            build_locked_keyboard(locked_rows, sid8, int(st2)) if locked_rows else None
        )
        await deliver_step_lock(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=session.last_step_message_id,
            session_id=result.session_id,
            step=int(st2),
            reply_markup=locked_keyboard,
        )
        logger.info("TG.6.4.07 keyboard=cleared msg_id=%s", session.last_step_message_id)
    if result.status == "duplicate":
        await deliver_step_view(
            message=message,
            step_view=result.step_view,
            session_id=result.session_id,
            step=result.step,
            theme_id=result.theme_id,
            total_steps=session.max_steps,
        )
        await _maybe_send_book_offer(message, result)
        await _clear_l3_free_text_state(state)
        return
    await message.answer(f"Твой выбор: {message.text}")
    await deliver_step_view(
        message=message,
        step_view=result.step_view,
        session_id=result.session_id,
        step=result.step,
        theme_id=result.theme_id,
        total_steps=session.max_steps,
    )
    await _maybe_send_book_offer(message, result)
    await state.set_state(L3.STEP)
    await _clear_l3_free_text_state(state)


@router.callback_query(lambda query: query.data == "go:shop")
async def on_go_shop(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await safe_callback_answer(callback)
        return
    if callback.message.chat.type != "private":
        await callback.message.answer("Я работаю только в личных сообщениях. Напиши мне в личку.")
        await safe_callback_answer(callback)
        return
    await state.set_state(L4.SHOP)
    await _send_shop_screen(callback.message)
    await safe_callback_answer(callback)


@router.callback_query(lambda query: query.data == "go:continue")
async def on_go_continue(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await safe_callback_answer(callback)
        return
    if not callback.from_user:
        await safe_callback_answer(callback)
        return
    await do_continue(callback.message, state, user_id=callback.from_user.id)
    try:
        await callback.message.bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=None,
        )
    except Exception:
        pass
    await safe_callback_answer(callback)


@router.message(Command("start"), StateFilter("*"))
async def on_start(message: Message, state: FSMContext) -> None:
    # /start = вход в "дом" бота (L1), не "начать сказку"
    logger.info("TG.6.4.10 cmd=/start outcome=menu_shown active=%s state=%s", 1 if has_active(message.from_user.id) else 0, await state.get_state())
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
