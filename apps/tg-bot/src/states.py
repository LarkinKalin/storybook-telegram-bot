from aiogram.fsm.state import State, StatesGroup


class UX(StatesGroup):
    l1 = State()
    l2 = State()


class L3(StatesGroup):
    STEP = State()
    FREE_TEXT = State()


class L4(StatesGroup):
    HELP = State()
    SHOP = State()
    SETTINGS = State()
    SETTINGS_CHILD_NAME = State()


class L5(StatesGroup):
    WHY_TEXT = State()
