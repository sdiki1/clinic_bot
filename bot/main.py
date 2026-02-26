from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.engine import make_url

from bot.config import get_settings
from bot.database import create_engine_and_session, init_db
from bot.handlers import router
from bot.middlewares import DbSessionMiddleware


def ensure_sqlite_dir(database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
        db_path = Path(url.database)
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)


async def run_bot() -> None:
    settings = get_settings()
    ensure_sqlite_dir(settings.database_url)

    engine, session_pool = create_engine_and_session(settings.database_url)
    await init_db(engine)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(router)
    dp.update.middleware(DbSessionMiddleware(session_pool))
    dp["settings"] = settings

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
