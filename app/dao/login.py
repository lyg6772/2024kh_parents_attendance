from app.util.db import DB
from sqlalchemy import text

class LoginDao:
    def __init__(self):
        self.db = DB()

    async def get_admin(self, user_name):
        query = """SELECT USER_PW 
        FROM user.KY_USER_L
        WHERE USER_ID = %(user_name)s
        LIMIT 1
        """
        async with self.db.get_db_session() as session:
            result = session.execute(query, {"user_name": user_name})
            return result['USER_PW']