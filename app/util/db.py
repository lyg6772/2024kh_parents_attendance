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
        url = f'oracle+oracledb://{config.DB_USER}:{config.DB_PW}@{config.ORACLE_CONNECTION_STRING}'
        self.engine = create_async_engine(url)
        self.session_local = sessionmaker(autoflush=True, bind=self.engine, class_=AsyncSession)

    async def get_db_session(self) -> AsyncSession:
        sess = self.session_local()
        try:
            yield sess
        finally:
            await sess.close()
