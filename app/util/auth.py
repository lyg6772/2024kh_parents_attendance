from app import config


from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException, Request




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


_auth_handler = AuthHandler()


def get_current_user(request: Request) -> str:
    """쿠키 JWT에서 user_id를 꺼내는 공용 인증 의존성. controller/agent 라우터 공용."""
    token = request.cookies.get("token", "")
    user_id = _auth_handler.decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return user_id
