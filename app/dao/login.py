from app.util.db import DB
from sqlalchemy import text
from fastapi import Depends


class LoginDao:
    def __init__(self, db_session=Depends(DB().get_db_session)):
        self.session = db_session

    async def get_password(self, user_name):
        query = text("""SELECT USER_PW 
        FROM user.KY_USER_L
        WHERE USER_ID = :user_name
        LIMIT 1
        """)
        async with self.session as session:
            result = await session.execute(query, {"user_name": user_name})
            return result.scalar_one_or_none()