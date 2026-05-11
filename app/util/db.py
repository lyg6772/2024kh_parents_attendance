from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app import config
from app.util.singleton import SingletonClass


class DB(SingletonClass):
    engine = None

    def __init__(self):
        super().__init__()

    def _build_url(self):
        if config.DB_URL:
            return config.DB_URL
        return f'oracle+oracledb://{config.DB_USER}:{config.DB_PW}@{config.ORACLE_CONNECTION_STRING}'

    def init_db(self):
        url = self._build_url()
        self.engine = create_async_engine(url)
        self.session_local = sessionmaker(autoflush=True, bind=self.engine, class_=AsyncSession)

    async def create_tables(self):
        from app.dao.tables import Base
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_db_session(self) -> AsyncSession:
        sess = self.session_local()
        try:
            yield sess
        finally:
            await sess.close()


async def get_session():
    async with DB().session_local() as session:
        yield session
