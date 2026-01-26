import asyncio
import logging
import os
import signal
import sys
import time

from aiohttp import ClientConnectionError, ServerDisconnectedError
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from src.handlers.l1 import router as l1_router
from src.handlers.l2 import router as l2_router
from src.handlers.why import router as why_router
from src.services.theme_registry import registry
from src.services.whyqa import whyqa

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
logger = logging.getLogger(__name__)

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(l1_router)


dp.include_router(l2_router)
dp.include_router(why_router)


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = logging.getLevelName(level_name)
    if isinstance(level, str):
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )


async def main() -> None:
    setup_logging()
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is empty. Put it into /etc/skazka/skazka.env (not in repo).")

    registry.load_all()
    whyqa.load()

    bot = Bot(token=BOT_TOKEN)
    logger.info("tg-bot started")
    stop_event = asyncio.Event()
    last_error_log_at = 0.0
    retry_count = 0

    def _handle_sigterm() -> None:
        if stop_event.is_set():
            return
        logger.warning("Received SIGTERM, shutting down polling.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handle_sigterm)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handle_sigterm())

    backoff_steps = [1, 2, 5, 10]
    while True:
        try:
            await dp.start_polling(bot)
            retry_count = 0
        except TelegramNetworkError:
            retry_count += 1
            now = time.time()
            if now - last_error_log_at > 10:
                logger.warning("Telegram network error during polling, retry #%s.", retry_count)
                last_error_log_at = now
        except (ServerDisconnectedError, ClientConnectionError, asyncio.TimeoutError) as exc:
            retry_count += 1
            now = time.time()
            if now - last_error_log_at > 10:
                logger.warning(
                    "Network error during polling (%s), retry #%s.",
                    type(exc).__name__,
                    retry_count,
                )
                last_error_log_at = now
        except asyncio.CancelledError:
            raise
        except Exception:
            retry_count += 1
            now = time.time()
            if now - last_error_log_at > 10:
                logger.exception("Unexpected polling error, retry #%s.", retry_count)
                last_error_log_at = now
        else:
            break
        if stop_event.is_set():
            break

        backoff_index = min(retry_count - 1, len(backoff_steps) - 1)
        await asyncio.sleep(backoff_steps[backoff_index])


if __name__ == "__main__":
    asyncio.run(main())
