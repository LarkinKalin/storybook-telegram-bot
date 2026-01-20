from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.handlers.l1 import open_l1
from src.keyboards.why import build_why_keyboard
from src.services.read_prefs import get_read_mode
from src.services.whyqa import whyqa
from src.states import L5, UX

router = Router(name="why")


@router.callback_query(lambda query: query.data == "go:l1")
async def on_go_l1(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(UX.l1)
    await open_l1(callback.message, state)
    await callback.answer()


@router.message(L5.WHY_TEXT)
async def on_why_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Я понимаю только текстовые вопросы.")
        await message.answer("Попробуй написать вопрос словами.", reply_markup=build_why_keyboard())
        return

    read_mode = get_read_mode(message.from_user.id)
    answer = whyqa.answer(message.text, read_mode)
    await message.answer(answer.text, reply_markup=build_why_keyboard())
    await state.set_state(L5.WHY_TEXT)
