from aiogram.fsm.state import State, StatesGroup


class UX(StatesGroup):
    l1 = State()
    l2 = State()


class L3(StatesGroup):
    STEP = State()


class L4(StatesGroup):
    HELP = State()
    SHOP = State()
    SETTINGS = State()


class L5(StatesGroup):
    WHY_TEXT = State()
