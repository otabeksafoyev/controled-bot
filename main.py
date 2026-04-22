"""Entrypoint — userbot va control botni bitta event loopda ishga tushiradi."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from aiogram import Bot

from bot.client import bot, dp
from bot.handlers import channels as channels_handlers
from bot.handlers import menu as menu_handlers
from bot.handlers import replies as replies_handlers
from config import settings
from db.engine import engine
from db.migrations import migrate_legacy_channel_links
from db.models import Base
from userbot.client import build_client
from userbot.handlers import register as register_userbot_handlers


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await migrate_legacy_channel_links(engine)


async def _run() -> None:
    _setup_logging()
    log = logging.getLogger("main")

    await _init_db()
    log.info("SQLite tayyor: %s", settings.SQLITE_PATH)

    userbot = build_client()
    register_userbot_handlers(userbot)
    await userbot.start()
    me = await userbot.get_me()
    log.info("Userbot ready: @%s (id=%s)", me.username, me.id)

    bot_me = await bot.get_me()
    log.info("Control bot ready: @%s (id=%s)", bot_me.username, bot_me.id)
    log.info("SECRET_CHANNEL_ID: %s", settings.SECRET_CHANNEL_ID)

    dp.include_router(menu_handlers.router)
    dp.include_router(channels_handlers.router)
    dp.include_router(replies_handlers.router)

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
