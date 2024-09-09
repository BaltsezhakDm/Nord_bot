from hashids import Hashids
import os

key = os.getenv('crypt_key')
hashids = Hashids(salt=key, min_length=8)


def encode_user_id(user_id):
    print(user_id)
    return hashids.encode(user_id)

def decode_user_id(encoded_id):
    decoded = hashids.decode(encoded_id)
    return decoded[0] if decoded else None

if __name__ == '__main__':
    
    hash = encode_user_id(1)
    print(hash)
    print(decode_user_id('NWJSSk5SeVc'))
