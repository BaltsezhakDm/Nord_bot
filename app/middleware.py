import logging
from aiogram.types import Update, InputMediaPhoto, FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from datetime import datetime
from keyboards import keyboard_main


from db import get_db_session
from model import LogEntry

logging.basicConfig(level=logging.INFO)


photo_nord = FSInputFile('files/nord.webp')
photo = InputMediaPhoto(media=photo_nord)


class ErrorHandlingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        # Получаем callback_query или message, если это не callback
        if event.callback_query:
            user_id = event.callback_query.from_user.id
        if event.message:
            user_id = event.message.from_user.id
        else:
            user_id = None
        
        try:
            # Выполнение хэндлера
            result = await handler(event, data)
            return result
        except Exception as e:
            # Логирование ошибки
            logging.error(f"Error for user {user_id}: {e}")

            # Отправляем сообщение пользователю о возникшей ошибке
            try:
                if event.message:
                    await event.message.bot.send_photo(
                        event.message.chat.id,
                        photo=photo_nord,
                        caption=f"Произошла ошибка. Поробуйте еще раз", 
                        reply_markup=keyboard_main,
                        )
                elif event.callback_query:
                    await event.callback_query.message.bot.send_photo(
                        event.callback_query.message.chat.id,
                        photo=photo_nord,
                        caption=f"Произошла ошибка. Поробуйте еще раз", 
                        reply_markup=keyboard_main,
                        )
            except Exception as send_error:
                logging.error(f"Failed to send error message to user {user_id}: {send_error}")
            # Повторно поднимем исключение, чтобы оно было обработано дальше, если нужно
            raise e


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

class LoggingMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        query = event.callback_query
        if query:
            user_id = query.from_user.id
            command = query.data
        elif event.message:
            user_id = event.message.from_user.id
            command = event.message.text
        else:
            user_id = None
            command = None
        
        logging.info(f"Start: User: {user_id}, Command: {command}")

        session = await get_db_session()  # Создаем сессию базы данных
        log_entry = LogEntry.create_log(
            user_id=user_id,
            command=command,
            status="Processing",
        )

        try:
            result = await handler(event, data)
            log_entry.status = "Success"
            logging.info(f"Success: User: {user_id}, Command: {command}")
            return result
        except Exception as e:
            log_entry.status = "Error"
            log_entry.error_message = str(e)
            logging.error(f"Error: User: {user_id}, Command: {command}, Exception: {e}")
        finally:
            session.add(log_entry)
            await session.commit()
            await session.close()

