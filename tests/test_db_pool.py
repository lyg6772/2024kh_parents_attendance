"""app/util/db.py의 pool_pre_ping/pool_recycle 검증.

두 층으로 나눈다:
1. `DB().init_db()`를 실제로 호출해 엔진에 두 설정값이 실려 있는지 확인 — 이게 지워지면
   바로 빨개진다.
2. sqlite+aiosqlite 파일 URL은 기본이 NullPool(체크아웃마다 새 커넥션)이라 pool_pre_ping이
   사실상 no-op이다 — 그래서 운영 Oracle 커넥션이 쓰는 것과 같은 풀 클래스
   (AsyncAdaptedQueuePool)을 강제해, "idle 중이던 커넥션이 DB/방화벽 쪽에서 조용히
   끊긴 뒤 재사용되는" 실제 장애 시나리오가 그 설정으로 복구되는지 재현한다.
"""

import tempfile

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.util.db import DB


async def test_init_db_sets_pool_pre_ping_and_recycle():
    # DB는 SingletonClass다 — init_db()를 여기서 다시 부르면 다른 테스트가 쓰는
    # engine/session_local을 프로세스 전역으로 덮어쓴다. 끝나면 원래 걸로 되돌리고
    # 이 테스트가 새로 만든 엔진은 dispose한다.
    old_engine, old_session_local = DB().engine, DB().session_local
    DB().init_db()
    try:
        assert DB().engine.pool._pre_ping is True
        assert DB().engine.pool._recycle == 1800
    finally:
        new_engine = DB().engine
        DB().engine, DB().session_local = old_engine, old_session_local
        await new_engine.dispose()


async def _kill_conn_after_checkin(pre_ping):
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{f.name}",
            poolclass=AsyncAdaptedQueuePool,
            pool_pre_ping=pre_ping,
        )
        # 커넥션을 건강한 채로 풀에 반납
        async with engine.connect() as conn:
            raw = await conn.get_raw_connection()
            driver_conn = raw.driver_connection

        # 풀 안에서 idle 상태로 있는 동안 몰래 끊는다 (SQLAlchemy는 이 시점엔 모른다)
        await driver_conn.close()

        try:
            async with engine.connect() as conn:
                await conn.exec_driver_sql("select 1")
            return True
        except DBAPIError:
            return False
        finally:
            await engine.dispose()


async def test_pool_pre_ping_recovers_dead_connection():
    assert await _kill_conn_after_checkin(pre_ping=True) is True


async def test_without_pool_pre_ping_dead_connection_fails():
    # 음성 대조: 이 설정 없이는 같은 시나리오가 실제로 깨진다는 것을 확인한다.
    assert await _kill_conn_after_checkin(pre_ping=False) is False
