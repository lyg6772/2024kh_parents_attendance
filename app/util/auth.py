from app import config


from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException




class AuthHandler:
    def __init__(self):
        pass

    def encode_token(self, user_id):
        payload = {
            'exp': datetime.now(tz=timezone.utc) + timedelta(hours=config.ACCESS_TOKEN_EXPIRE_HOURS),
            'iat': datetime.now(tz=timezone.utc),
            'sub': user_id
        }
        return jwt.encode(
            payload,
            config.SECRET_SALT,
            algorithm='HS256'
        )

    def decode_token(self, token):
        try:
            payload = jwt.decode(token, config.SECRET_SALT, algorithms=['HS256'])
            return payload['sub']
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail='Signature has expired')
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail='Invalid token')
