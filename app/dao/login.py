from app.util.db import DB
from fastapi import Depends

from app.dao import functions as dao_fn


class LoginDao:
    def __init__(self, db_session=Depends(DB().get_db_session)):
        self.session = db_session

    async def get_password(self, user_name):
        async with self.session as session:
            return await dao_fn.get_password(session, user_name)
