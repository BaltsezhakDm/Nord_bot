import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import asyncio

from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from db import get_db_session
from model import Places
from middleware import DbSessionMiddleware, LoggingMiddleware, ErrorHandlingMiddleware
from endpoints import router

logging.basicConfig(level=logging.ERROR)
logging.basicConfig()
logging.getLogger('pika').setLevel(logging.ERROR)


token = os.getenv('token')
webhook_url = os.getenv('webhook_url')


bot = Bot(token=token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


    
dp.update.middleware(DbSessionMiddleware())
dp.update.middleware(LoggingMiddleware())
dp.update.middleware(ErrorHandlingMiddleware())


dp.include_router(router)


async def on_startup():
    session = await get_db_session()
    await Places.create(session, 'Комендантский 65')
    await Places.create(session, 'Бородинская 2\86')
    await bot.set_webhook(webhook_url)

    # await init_db()

def main() -> None:

    dp.startup.register(on_startup)

    app = web.Application()

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path='/telegram')

    setup_application(app, dp, bot=bot)

    web.run_app(app, host='0.0.0.0', port='8000')

async def debug() -> None:
    await bot.delete_webhook()
    session = await get_db_session()
    await Places.create(session, 'Комендантский 65')
    await Places.create(session, 'Бородинская 2\86')
    await dp.start_polling(bot)


if __name__ == '__main__':
    if os.getenv('DEBUG', False):
        asyncio.run(debug())
    else:
        main()
