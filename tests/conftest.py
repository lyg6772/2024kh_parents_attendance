"""테스트 공통 fixture.

**이 블록은 `app.*` import 보다 먼저 와야 한다.** `app/config.py` 는 import 시점에
`os.getcwd()/app/.env` 를 읽고 `SECRET_SALT` 가 없으면 RuntimeError 를 던진다.
그리고 `load_dotenv` 는 기본이 `override=False` 라 **먼저 세운 값이 이긴다** —
즉 여기서 세우면 개발자의 `.env` 가 이를 덮지 못한다. 그것이 의도다:

- JWT 검증은 **알려진 salt** 가 있어야 재현된다. 개발자 비밀을 쓰면 머신마다 결과가 갈린다.
- `DB_URL` 을 여기서 sqlite 로 고정해 테스트가 실 DB 에 붙는 경로를 구조적으로 막는다.
- LLM 키를 비워 테스트가 **외부 유료 호출을 내지 않게** 한다. 실측 2026-08-02: 비우기
  전에는 개발자 키로 실제 Groq 호출이 나갔다.

`app/config.py` ↔ cwd ↔ `load_dotenv(override=False)` 결합은
`.agents/context/codebase-conventions.md` § 숨은 결합 이 소유한다.
"""

import os
import tempfile

_DB_FILE = os.path.join(tempfile.gettempdir(), "moru_oracle_test.db")

# `:memory:` 를 쓰지 않는 이유: in-memory sqlite 는 **커넥션마다 별개 DB** 라
# fixture 가 만든 테이블을 라우트의 세션이 못 본다 (실측: `no such table`).
TEST_ENV = {
    "SECRET_SALT": "moru-oracle-test-salt",
    "DB_URL": f"sqlite+aiosqlite:///{_DB_FILE}",
    "ACCESS_TOKEN_EXPIRE_HOURS": "8",
    "GROQ_API_KEY": "",
    "GEMINI_API_KEY": "",
}
os.environ.update(TEST_ENV)

# ruff: noqa: E402  — 위 환경 설정이 반드시 앱 import 보다 앞서야 한다
import httpx
import pytest
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.dao.tables import Base, KyUserL
from app.main import app as fastapi_app
from app.util.auth import AuthHandler
from app.util.db import DB, get_session

ADMIN_ID = "admin"
ADMIN_PW = "admin"


@pytest.fixture
async def db_session():
    """기존 유닛 테스트용 — 건드리지 않는다."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def http_db():
    """HTTP 테스트용 sqlite 파일. 세션 스코프 — 매 테스트 재생성은 비싸다."""
    if os.path.exists(_DB_FILE):
        os.remove(_DB_FILE)
    yield _DB_FILE
    if os.path.exists(_DB_FILE):
        os.remove(_DB_FILE)


@pytest.fixture
async def seeded_app(http_db):
    """테이블 생성 + admin 시드 + 의존성 오버라이드.

    `httpx.ASGITransport` 는 **lifespan 을 돌리지 않는다**(실측). 앱을 실기동하면
    도는 `create_tables`·`_seed_admin_user` 가 테스트에서는 안 뜨므로 여기서 대신한다.

    오버라이드 **키가 둘**이다: DAO 3파일은 `DB().get_db_session`, agent 라우터는
    `get_session`. 하나만 걸면 `/agent/*` 만 실 DB 로 샌다.
    """
    db = DB()
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db.session_local() as session:
        existing = await session.get(KyUserL, ADMIN_ID)
        if existing is None:
            pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
            session.add(KyUserL(user_id=ADMIN_ID, user_pw=pwd.hash(ADMIN_PW)))
            await session.commit()

    async def _override_session():
        async with db.session_local() as session:
            yield session

    fastapi_app.dependency_overrides[db.get_db_session] = _override_session
    fastapi_app.dependency_overrides[get_session] = _override_session
    try:
        yield fastapi_app
    finally:
        # 전역 상태를 남기면 기존 242개가 이 오버라이드를 물고 돈다.
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def client(seeded_app):
    """토큰 없는 클라이언트. 리다이렉트를 따라가지 않는다 — 307 자체가 관측 대상이다."""
    transport = httpx.ASGITransport(app=seeded_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", follow_redirects=False
    ) as c:
        yield c


@pytest.fixture
def valid_token():
    """앱과 **같은 경로**로 만든다 — 손으로 만들면 알고리즘·클레임이 갈린다."""
    return AuthHandler().encode_token(ADMIN_ID)


@pytest.fixture
async def admin_client(seeded_app, valid_token):
    transport = httpx.ASGITransport(app=seeded_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
        cookies={"token": valid_token},
    ) as c:
        yield c
