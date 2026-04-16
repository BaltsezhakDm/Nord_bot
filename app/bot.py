import logging
import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web

from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from db import get_db_session
from model import Places
from middleware import DbSessionMiddleware, LoggingMiddleware, ErrorHandlingMiddleware
from endpoints import router
from settings import settings

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger('pika').setLevel(logging.ERROR)

# Инициализация бота с поддержкой прокси
session = AiohttpSession(proxy=settings.PROXY_URL) if settings.PROXY_URL else None
bot = Bot(token=settings.BOT_TOKEN, session=session)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Регистрация middleware
dp.update.middleware(DbSessionMiddleware())
dp.update.middleware(LoggingMiddleware())
dp.update.middleware(ErrorHandlingMiddleware())

# Подключение роутеров
dp.include_router(router)

async def on_startup():
    db_session = await get_db_session()
    places = ['Комендантский 65', 'Аптекарский 5', 'Бородинская 2\\86']
    for place_name in places:
        await Places.create(db_session, place_name)

    if settings.WEBHOOK_URL:
        await bot.set_webhook(settings.WEBHOOK_URL)
    logging.info("Bot started")

def main() -> None:
    dp.startup.register(on_startup)
    app = web.Application()

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path='/telegram')

    setup_application(app, dp, bot=bot)
    web.run_app(app, host='0.0.0.0', port=8000)

async def debug() -> None:
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
        main()
