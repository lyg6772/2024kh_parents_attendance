from fastapi import FastAPI, Request
from app.util.db import DB
from app.controller.router import router
from app.agent.router import agent_router
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from app import config


def create_app():
    app = FastAPI()

    DB().init_db()

    if config.DB_URL and "sqlite" in config.DB_URL and "local" in config.DB_URL:
        @app.on_event("startup")
        async def _create_tables():
            await DB().create_tables()
            await _seed_admin_user()

    app.include_router(router)
    app.include_router(agent_router)
    return app


async def _seed_admin_user():
    from passlib.context import CryptContext
    from sqlalchemy import select
    from app.dao.tables import KyUserL

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    async with DB().session_local() as session:
        exists = await session.execute(select(KyUserL).where(KyUserL.user_id == "admin"))
        if exists.scalar_one_or_none() is None:
            session.add(KyUserL(user_id="admin", user_pw=pwd_context.hash("admin")))
            await session.commit()


app = create_app()


@app.get("/")
def health_check():
    return {"200": "ok"}


@app.exception_handler(401)
def except_unauthorized_handling(request: Request, exc: HTTPException):
    return RedirectResponse(url='/login')
