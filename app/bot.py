import logging
import os
from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.dispatcher.middlewares.base import BaseMiddleware

from db import get_db_session, init_db
from model import Places
from endpoints import router

logging.basicConfig(level=logging.DEBUG)

token = os.getenv('token')


bot = Bot(token=token)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class DbSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        data['session'] = await get_db_session()
        try:
            return await handler(event, data)
        except Exception as e:
            session: AsyncSession = data.get('session')
            await session.rollback()
            print(e)
        finally:
            session: AsyncSession = data.get('session')
            if session:
                await session.close()


dp.update.middleware(DbSessionMiddleware())


dp.include_router(router)


async def on_startup():
    session = await get_db_session()
    await Places.create(session, 'Комендантский 65')
    await Places.create(session, 'Бородинская 2\86')
    # await init_db()

if __name__ == '__main__':
    dp.startup.register(on_startup)
    dp.run_polling(bot, skip_updates=True)
