from __future__ import annotations

from time import time

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from src.keyboards.l1 import build_l1_keyboard
from src.keyboards.l2 import build_l2_keyboard
from src.keyboards.l3 import build_l3_keyboard
from src.keyboards.confirm import build_new_story_confirm_keyboard
from src.services.runtime_sessions import (
    finish_session,
    get_session,
    has_active,
    start_session,
    touch_last_step,
)
from src.services.theme_registry import registry
from src.states import L3, UX

router = Router(name="l2")


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
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=build_l1_keyboard(has_active(callback.from_user.id)),
    )
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
        await callback.answer("Тема устарела")
        await _render_l2(callback.message, 0, edit=True)
        return
    if has_active(callback.from_user.id):
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
    await callback.answer()


@router.callback_query(lambda query: query.data and query.data.startswith("new:yes:"))
async def on_new_story_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    if not callback.from_user:
        await callback.answer()
        return
    theme_id = callback.data.split(":", 2)[2] if callback.data else ""
    theme = registry.get_theme(theme_id)
    if not theme:
        await callback.answer("Тема устарела")
        await _render_l2(callback.message, 0, edit=True)
        return
    session = get_session(callback.from_user.id)
    if session and session.last_step_message_id:
        try:
            await callback.message.bot.edit_message_reply_markup(
                chat_id=callback.message.chat.id,
                message_id=session.last_step_message_id,
                reply_markup=None,
            )
        except Exception:
            pass
    finish_session(callback.from_user.id)
    await _start_theme_session(callback.message, state, callback.from_user.id, theme)
    await callback.answer()


async def _start_theme_session(
    message: Message, state: FSMContext, tg_id: int, theme: dict[str, str]
) -> None:
    await state.update_data(theme_id=theme["id"], style_id=theme["style_default"])
    start_session(tg_id, theme["id"], max_steps=1)
    step_text = f"Шаг 1/1. Тема: {theme['title']}. История появится в следующем квесте."
    sent_message = await message.answer(step_text, reply_markup=ReplyKeyboardRemove())
    try:
        await message.bot.edit_message_reply_markup(
            chat_id=sent_message.chat.id,
            message_id=sent_message.message_id,
            reply_markup=build_l3_keyboard(),
        )
    except Exception:
        pass
    touch_last_step(tg_id, sent_message.message_id, int(time()))
    await state.set_state(L3.STEP)
