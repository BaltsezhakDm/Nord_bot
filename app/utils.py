from hashids import Hashids
from functools import wraps
from logger import setup_logger
from aiogram.types import Message
import os
import json
import base64
import zlib
from db import get_db_session
from model import LogEntry

key = os.getenv('crypt_key', '')
hashids = Hashids(salt=key, min_length=8)
logger = setup_logger()

def encode_user_id(user_id):
    return hashids.encode(user_id)

def decode_user_id(encoded_id):
    decoded = hashids.decode(encoded_id)
    return decoded[0] if decoded else None

def encode_json(obj):
    json_str = json.dumps(obj, separators=(',', ':'))
    compressed_data = zlib.compress(json_str.encode('utf-8'))
    encoded = base64.urlsafe_b64encode(compressed_data).decode('utf-8')
    return encoded

def decode_json(encoded_str):
    compressed_data = base64.urlsafe_b64decode(encoded_str)
    json_str = zlib.decompress(compressed_data).decode('utf-8')
    return json.loads(json_str)


def check_referal(func):
    @wraps(func)
    async def wrapper(message: Message, session, state, *args, **kwargs):
        start_link = message.md_text.split()
        user_id = message.chat.id
    
        if len(start_link) == 2:
            logger.debug(f"Received ref link: {start_link[1]}")
            log_entry = LogEntry.create_log(
                    user_id=user_id,
                    command="start with ref link",
                )
            
            ref_data = start_link[1]
            data = {"place_id": None, "user_id": None}
            
            try:
                # Attempt to decode place data
                place_data = decode_json(ref_data)
                if isinstance(place_data, dict) and "place" in place_data:
                    data["place_id"] = place_data["place"]
                    log_entry.status = "Success"
                    logger.debug(f"Извлечено place_id: {data['place_id']}")
                else:
                    log_entry.status = "Error"
                    log_entry.error_message = f"Неверная ссылка реферала {ref_data}"
                    logger.warning(f"Ошибка при декодировании place_data: {place_data}")
            except Exception as e:
                logger.debug(f"Ошибка при декодировании place_data. Попытка декодирования user_id. Error: {e}")
                try:
                    # Attempt to decode user ID
                    data["user_id"] = decode_user_id(ref_data)
                    log_entry.status = "Success"
                    logger.debug(f"Извлечено user_id: {data['user_id']}")
                except (ValueError, KeyError, TypeError) as inner_e:
                    log_entry.status = "Error"
                    log_entry.error_message = f"Неверная ссылка реферала {ref_data}"
                    logger.error(f"Ошибка при декодировании user_id: {inner_e}")

            finally:
                session = await get_db_session()  # Создаем сессию базы данных
                session.add(log_entry)
                await session.commit()
                await session.close()
                
            
            return await func(message, session, state, referal_data=data, *args, **kwargs)
        
        logger.debug("Нет реферальных данных.")
        return await func(message, session, state, referal_data={}, *args, **kwargs)
    return wrapper
