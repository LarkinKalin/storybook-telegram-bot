from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from src.keyboards.l1 import L1Label, build_l1_keyboard
from src.services.runtime_sessions import has_active, set_active
from src.states import UX

router = Router(name="l1")


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
    await open_l1(message, state)


@router.message(UX.l1)
async def l1_any(message: Message, state: FSMContext) -> None:
    """
    Критическое правило UX-10:
    - ReplyKeyboard = текст.
    - СНАЧАЛА матчимся по лейблам кнопок.
    - И только потом считаем ввод "произвольным".
    - Любой неизвестный ввод в L1 -> подсказка + повтор L1, без смены состояния.
    """
    if not message.text:
        await message.answer("Мне нужен текст или кнопки. Остальное оставь для переписки с космосом.")
        await message.answer("🏠 Главное меню", reply_markup=build_l1_keyboard(has_active(message.from_user.id)))
        return

    text = message.text.strip()

    # 1) СНАЧАЛА: кнопочные команды (строго по лейблам)
    if text == L1Label.START.value:
        # Заглушка маршрутизации (пока нет L2): считаем, что "активная" появилась.
        set_active(message.from_user.id, True)
        await message.answer("▶ Начать сказку → заглушка (дальше будет L2: выбор темы).", reply_markup=ReplyKeyboardRemove())
        await open_l1(message, state)
        return

    if text == L1Label.CONTINUE.value:
        await message.answer("⏩ Продолжить → заглушка (дальше будет /resume и CONTINUE в L3).", reply_markup=ReplyKeyboardRemove())
        await open_l1(message, state)
        return

    if text == L1Label.MY.value:
        await message.answer("🧩 Мои сказки → заглушка.", reply_markup=ReplyKeyboardRemove())
        await open_l1(message, state)
        return

    if text == L1Label.SHOP.value:
        await message.answer("🛒 Магазин → заглушка.", reply_markup=ReplyKeyboardRemove())
        await open_l1(message, state)
        return

    if text == L1Label.HELP.value:
        await message.answer("❓ Помощь → заглушка.", reply_markup=ReplyKeyboardRemove())
        await open_l1(message, state)
        return

    if text == L1Label.SETTINGS.value:
        await message.answer("⚙ Настройки → заглушка.", reply_markup=ReplyKeyboardRemove())
        await open_l1(message, state)
        return

    # 2) Потом: "произвольный" неизвестный ввод
    await message.answer(
        "Не понял. Используй кнопки меню или команды /start /help.",
    )
    # Важно: состояние НЕ меняем (оно уже UX.l1). Просто повторяем L1.
    await message.answer(
        "🏠 Главное меню",
        reply_markup=build_l1_keyboard(has_active(message.from_user.id)),
    )
