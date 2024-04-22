from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
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
        self.session_local = sessionmaker(autoflush=True, bind=self.engine, class_=AsyncSession)

    async def get_db_session(self) -> AsyncSession:
        sess = self.session_local()
        try:
            yield sess
        finally:
            await sess.close()
