from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.keyboards.why import build_why_keyboard
from src.services.read_prefs import get_read_mode
from src.services.why_text import answer_why_text
from src.states import L5

router = Router(name="why")


@router.message(L5.WHY_TEXT)
async def on_why_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Я понимаю только текстовые вопросы.")
        await message.answer("Попробуй написать вопрос словами.", reply_markup=build_why_keyboard())
        return

    read_mode = get_read_mode(message.from_user.id)
    result = answer_why_text(message.text, read_mode)
    await message.answer(result.text, reply_markup=build_why_keyboard())
    await state.set_state(L5.WHY_TEXT)
