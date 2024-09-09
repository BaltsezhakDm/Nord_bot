from hashids import Hashids
import os
import json
import base64
import zlib

key = os.getenv('crypt_key', '')
hashids = Hashids(salt=key, min_length=8)


def encode_user_id(user_id):
    print(user_id)
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

if __name__ == '__main__':
    
    data = {'place': 2}
    
    # Кодирование
    encoded = encode_json(data)
    print(f'Encoded: {encoded}')

    # Декодирование
    decoded = decode_json(encoded)
    print(f'Decoded: {decoded}')
