"""Entrypoint — userbot va control botni bitta event loopda ishga tushiradi."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from aiogram import Bot

from bot.client import bot, dp
from bot.handlers import admin as admin_handlers
from bot.handlers import ingest as ingest_handlers
from config import settings
from userbot.client import build_client
from userbot.handlers import register as register_userbot_handlers
from userbot.handlers import set_bot_username


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _run() -> None:
    _setup_logging()
    log = logging.getLogger("main")

    userbot = build_client()
    register_userbot_handlers(userbot)
    await userbot.start()  # StringSession yoki mavjud fayl asosidagi sessiya
    me = await userbot.get_me()
    log.info("Userbot ready: @%s (id=%s)", me.username, me.id)

    # Control bot username — userbot moslik topilganda videoni shu yerga yuboradi
    bot_me = await bot.get_me()
    if not bot_me.username:
        raise RuntimeError("Control botda username yo'q — @BotFather orqali belgilang")
    set_bot_username(bot_me.username)
    log.info("Control bot ready: @%s (id=%s)", bot_me.username, bot_me.id)

    # Routerlar — bir marta
    dp.include_router(admin_handlers.router)
    dp.include_router(ingest_handlers.router)

    stop_event = asyncio.Event()

    def _stop(*_: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _stop)

    async def _run_bot(bot_instance: Bot) -> None:
        await dp.start_polling(bot_instance, userbot=userbot)

    bot_task = asyncio.create_task(_run_bot(bot), name="control-bot")
    ub_task = asyncio.create_task(userbot.run_until_disconnected(), name="userbot")  # type: ignore[arg-type]
    stop_task = asyncio.create_task(stop_event.wait(), name="stop")

    done, _pending = await asyncio.wait({bot_task, ub_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    log.info("Shutting down (task done: %s)", [t.get_name() for t in done])

    await dp.stop_polling()
    await bot.session.close()
    if userbot.is_connected():
        await userbot.disconnect()  # type: ignore[func-returns-value]

    for task in (bot_task, ub_task):
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
