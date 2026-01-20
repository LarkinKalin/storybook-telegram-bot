from aiogram.fsm.state import State, StatesGroup


class UX(StatesGroup):
    l1 = State()
    l2 = State()


class L5(StatesGroup):
    WHY_TEXT = State()
