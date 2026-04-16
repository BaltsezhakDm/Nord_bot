import logging
from aiogram.types import Update, FSInputFile
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from keyboards import keyboard_main
from db import get_db_session
from model import LogEntry

logger = logging.getLogger(__name__)

PHOTO_NORD = FSInputFile('files/nord.webp')

class ErrorHandlingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            user_id = event.from_user.id if event.from_user else "Unknown"
            logger.exception(f"Error for user {user_id}: {e}")

            message = event.message or (event.callback_query.message if event.callback_query else None)
            if message:
                try:
                    await message.answer_photo(
                        photo=PHOTO_NORD,
                        caption="Произошла ошибка. Попробуйте еще раз.",
                        reply_markup=keyboard_main,
                    )
                except Exception:
                    logger.error("Failed to send error message to user")
            raise e

class DbSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        async with await get_db_session() as session:
            data['session'] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                raise e

class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id if event.from_user else None
        command = None
        if event.message:
            command = event.message.text
        elif event.callback_query:
            command = event.callback_query.data

        logger.info(f"Start: User: {user_id}, Command: {command}")
        
        log_entry = LogEntry.create_log(
            user_id=user_id,
            command=command,
            status="Processing",
        )

        session: AsyncSession = data['session']
        session.add(log_entry)

        try:
            result = await handler(event, data)
            log_entry.status = "Success"
            return result
        except Exception as e:
            log_entry.status = "Error"
            log_entry.error_message = str(e)
            raise e
        finally:
            # Commit happens in DbSessionMiddleware
            logger.info(f"End: User: {user_id}, Command: {command}, Status: {log_entry.status}")
