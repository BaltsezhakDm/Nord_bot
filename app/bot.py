import logging
import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web
from aiohttp_socks import ProxyConnector

from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from db import get_db_session
from model import Places
from middleware import DbSessionMiddleware, LoggingMiddleware, ErrorHandlingMiddleware
from endpoints import router
from settings import settings
from utils import get_connector

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def init_bot():
    # Инициализация бота с поддержкой прокси
    if settings.PROXY_URL:
        if settings.PROXY_URL.startswith('socks'):
            connector = ProxyConnector.from_url(settings.PROXY_URL)
            session = AiohttpSession(connector=connector)
        else:
            session = AiohttpSession(proxy=settings.PROXY_URL)
    else:
        session = None

    bot = Bot(token=settings.BOT_TOKEN, session=session)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрация middleware
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(ErrorHandlingMiddleware())

    # Подключение роутеров
    dp.include_router(router)

    return bot, dp

async def on_startup(bot: Bot):
    db_session = await get_db_session()
    places = ['Комендантский 65', 'Аптекарский 5', 'Бородинская 2\\86']
    for place_name in places:
        await Places.create(db_session, place_name)

    if settings.WEBHOOK_URL:
        await bot.set_webhook(settings.WEBHOOK_URL)
    logging.info("Bot started")

async def main() -> None:
    bot, dp = await init_bot()
    dp.startup.register(on_startup)
    app = web.Application()

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path='/telegram')

    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    try:
        site = web.TCPSite(runner, host='0.0.0.0', port=8000)
        await site.start()
        logging.info("Bot started on 0.0.0.0:8000")
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()

async def debug() -> None:
    bot, dp = await init_bot()
    await bot.delete_webhook()
    db_session = await get_db_session()
    places = ['Комендантский 65', 'Аптекарский 5', 'Бородинская 2\\86']
    for place_name in places:
        await Places.create(db_session, place_name)

    logging.info("Starting polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    if settings.DEBUG:
        asyncio.run(debug())
    else:
        asyncio.run(main())
