from aiogram import types
from functools import wraps
from sqlalchemy.ext.asyncio import AsyncSession

from model import Customers
from logger import setup_logger

logger = setup_logger()

def login_required(func):
    @wraps(func)
    async def wrapper(message: types.Message, session: AsyncSession, *args, **kwargs):
        client = await Customers.find(message.chat.id, session)
        if client:
            return await func(message, session, client, *args, **kwargs)
        else:
            await message.answer(text='Вы не вошли. Введите команду /start')
    return wrapper

def admin_required(func):
    @wraps(func)
    async def wrapper(message: types.Message, session: AsyncSession, *args, **kwargs):
        client = await Customers.find(message.chat.id, session)
        if client and client.phone_number in (9969290700, 9216539725):
            return await func(message, session, client, *args, **kwargs)
        else:
            await message.answer(text='Нет прав доступа')
    return wrapper

def login_required_callback(func):
    @wraps(func)
    async def wrapper(call: types.CallbackQuery, session: AsyncSession, *args, **kwargs):
        client = await Customers.find(call.from_user.id, session)
        if client:
            return await func(call, session, client, *args, **kwargs)
        else:
            await call.message.answer(text='Вы не вошли. Введите команду /start')
    return wrapper