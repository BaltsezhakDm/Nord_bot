from hashids import Hashids
from functools import wraps
from logger import setup_logger
import os
import json
import base64
import zlib

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
    def wrapper(message, session, state, *args, **kwargs):
        start_link = message.md_text.split()
        if len(start_link) == 2:
            logger.debug(f'Ref link: {start_link[1]}')
            try:
                place = decode_json(str(start_link[1]))
                if isinstance(place, dict):
                    place = place['place']
                logger.debug(f'(place): {place}')
                data = dict(place_id=place, user_id=None)
            except:
                user_id = decode_user_id(str(start_link[1]))
                logger.debug(f'(user): {user_id}')
                data = dict(place_id=None, user_id=user_id)
            return func(message, session, state, referal_data=data, *args, **kwargs)
        else:
            return func(message, session, state, referal_data={}, *args, **kwargs)
    return wrapper
