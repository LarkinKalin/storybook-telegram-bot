import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from src.handlers.l1 import router as l1_router
from src.handlers.l2 import router as l2_router
from src.handlers.why import router as why_router
from src.services.theme_registry import registry
from src.services.whyqa import whyqa

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(l1_router)


dp.include_router(l2_router)
dp.include_router(why_router)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty. Put it into /etc/skazka/skazka.env (not in repo).")

    registry.load_all()
    whyqa.load()

    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
