import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer("Сказка-бот запущен. /new чтобы начать (пока заглушка).")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty. Put it into /etc/skazka/skazka.env (not in repo).")

    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
