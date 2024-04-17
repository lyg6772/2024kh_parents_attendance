from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.engine import URL
from typing import Optional
from app import config
from app.util.singleton import SingletonClass


class DB(SingletonClass):
    engine = None

    def __init__(self):
        super().__init__()

    def init_db(self):
        url = URL.create(
            drivername="mysql+aiomysql",
            username=config.DB_USER,
            password=config.DB_PW,
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_DB
        )
        self.engine = create_async_engine(url)

    async def get_db_session(self) -> AsyncSession:
        sess = AsyncSession(bind=self.engine, dictionary=True)
        try:
            yield sess
        finally:
            await sess.close()
