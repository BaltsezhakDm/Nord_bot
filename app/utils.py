from hashids import Hashids
from functools import wraps
import logging
from aiogram.types import Message
import os
import json
import base64
import zlib
from db import get_db_session
from model import LogEntry
from settings import settings

logger = logging.getLogger(__name__)
hashids = Hashids(salt=settings.CRYPT_KEY, min_length=8)

def encode_user_id(user_id):
    return hashids.encode(user_id)

def decode_user_id(encoded_id):
    try:
        decoded = hashids.decode(encoded_id)
        return decoded[0] if decoded else None
    except Exception:
        return None

def encode_json(obj):
    json_str = json.dumps(obj, separators=(',', ':'))
    compressed_data = zlib.compress(json_str.encode('utf-8'))
    return base64.urlsafe_b64encode(compressed_data).decode('utf-8')

def decode_json(encoded_str):
    try:
        compressed_data = base64.urlsafe_b64decode(encoded_str)
        json_str = zlib.decompress(compressed_data).decode('utf-8')
        return json.loads(json_str)
    except Exception:
        return None

def check_referal(func):
    @wraps(func)
    async def wrapper(message: Message, session, state, *args, **kwargs):
        parts = message.md_text.split()
        user_id = message.chat.id
    
        referal_data = {}
        if len(parts) == 2:
            ref_payload = parts[1]
            logger.info(f"Received ref payload: {ref_payload}")
            
            # Попытка декодирования как JSON (для мест/QR)
            decoded_json = decode_json(ref_payload)
            if decoded_json and isinstance(decoded_json, dict):
                referal_data["place_id"] = decoded_json.get("place")
            else:
                # Попытка декодирования как ID пользователя
                decoded_uid = decode_user_id(ref_payload)
                if decoded_uid:
                    referal_data["user_id"] = decoded_uid

            log_entry = LogEntry.create_log(
                user_id=user_id,
                command=f"start with ref: {ref_payload}",
                status="Success" if referal_data else "Error"
            )
            session.add(log_entry)
            await session.commit()
            
        return await func(message, session, state, referal_data=referal_data, *args, **kwargs)
    return wrapper
