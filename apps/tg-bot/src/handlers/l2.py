from __future__ import annotations

import logging
from time import time

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from src.keyboards.l1 import build_l1_keyboard
from src.keyboards.l2 import build_l2_keyboard
from src.keyboards.confirm import build_new_story_confirm_keyboard
from src.services.runtime_sessions import get_session, has_active, start_session, touch_last_step
from src.services.story_runtime import render_step
from src.services.theme_registry import registry
from src.services.ui_delivery import _normalize_content
from src.services.image_delivery import resolve_story_step_ui, schedule_image_delivery
from src.states import L3, UX

router = Router(name="l2")
logger = logging.getLogger(__name__)


def _req_id_from_update(message: Message | None, callback: CallbackQuery | None) -> str | None:
    if callback and getattr(callback, "id", None):
        return str(callback.id)
    if message and getattr(message, "message_id", None):
        return str(message.message_id)
    return None


async def _handle_db_error(message: Message, state: FSMContext) -> None:
    logger.exception("DB operation failed")
    await message.answer("⚠️ База данных временно недоступна. Попробуй позже.")
    await state.set_state(UX.l1)
    await message.answer("🏠 Главное меню", reply_markup=build_l1_keyboard(False))


async def open_l2(message: Message, state: FSMContext, page_index: int = 0) -> None:
    await state.set_state(UX.l2)
    await _render_l2(message, page_index, edit=False)


def _clamp_page(raw_page: str | None) -> int:
    try:
        return int(raw_page or 0)
    except (TypeError, ValueError):
        return 0


async def _render_l2(message: Message, page_index: int, edit: bool) -> None:
    themes, page_index_clamped, page_count = registry.page(page_index, page_size=10)
    if not themes:
        text = "Пока нет доступных тем."
        markup = build_l2_keyboard(0, 0)
    else:
        text = "Выберите тему"
        markup = build_l2_keyboard(page_index_clamped, page_count)

    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(lambda query: query.data == "menu")
async def on_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        await callback.answer()
        return
    await state.set_state(UX.l1)
    try:
        active = has_active(callback.from_user.id)
    except Exception:
        await _handle_db_error(callback.message, state)
        return
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=build_l1_keyboard(active),
    )
    await callback.answer()


@router.callback_query(lambda query: query.data == "go:l2")
async def on_go_l2(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(UX.l2)
    await _render_l2(callback.message, 0, edit=True)
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("pg2:"))
async def on_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    raw_page = callback.data.split(":", 1)[1] if callback.data else "0"
    page_index = _clamp_page(raw_page)
    await state.set_state(UX.l2)
    await _render_l2(callback.message, page_index, edit=True)
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("t:"))
async def on_theme(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    if not callback.from_user:
        await callback.answer()
        return
    theme_id = callback.data.split(":", 1)[1] if callback.data else ""
    theme = registry.get_theme(theme_id)
    if not theme:
        await _render_l2(callback.message, 0, edit=True)
        return
    try:
        active = has_active(callback.from_user.id)
    except Exception:
        await _handle_db_error(callback.message, state)
        return
    if active:
        confirm_text = (
            "У тебя уже идёт сказка. Начать новую? Старая будет завершена."
        )
        await callback.message.answer(
            confirm_text,
            reply_markup=build_new_story_confirm_keyboard(theme["id"]),
        )
        await callback.answer()
        return

    await _start_theme_session(callback.message, state, callback.from_user.id, theme)


@router.callback_query(lambda query: query.data and query.data.startswith("new:yes:"))
async def on_new_story_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Ок")
    if not callback.message:
        return
    if not callback.from_user:
        return
    theme_id = callback.data.split(":", 2)[2] if callback.data else ""
    theme = registry.get_theme(theme_id)
    if not theme:
        await _render_l2(callback.message, 0, edit=True)
        return
    try:
        session = get_session(callback.from_user.id)
    except Exception:
        await _handle_db_error(callback.message, state)
        return
    if session and session.last_step_message_id:
        try:
            await callback.message.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=session.last_step_message_id,
                reply_markup=None,
            )
        except Exception:
            pass
    await _start_theme_session(callback.message, state, callback.from_user.id, theme)


async def _start_theme_session(
    message: Message, state: FSMContext, tg_id: int, theme: dict[str, str]
) -> None:
    await state.update_data(theme_id=theme["id"], style_id=theme["style_default"])
    try:
        start_session(tg_id, theme["id"], max_steps=8)
    except Exception:
        await _handle_db_error(message, state)
        return
    try:
        session = get_session(tg_id)
    except Exception:
        await _handle_db_error(message, state)
        return
    if not session:
        await _handle_db_error(message, state)
        return
    step_view = render_step(session.__dict__, req_id=_req_id_from_update(message, None))
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
        touch_last_step(tg_id, step_message.message_id, int(time()))
    except Exception:
        await _handle_db_error(message, state)
        return
    scene_brief = step_view.image_prompt
    if not scene_brief:
        normalized = _normalize_content(step_text)
        scene_brief = normalized[:200] if normalized else None
    # Engine step is zero-based; UI/story step index is step0 + 1.
    story_step_ui = resolve_story_step_ui(session.step)
    step_ui = story_step_ui
    logger.warning(
        "TG.7.4.01 entrypoint l2_render_step schedule_image_delivery session_id=%s step_ui=%s story_step_ui=%s",
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
    await state.set_state(L3.STEP)
