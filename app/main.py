from fastapi import FastAPI, Request
from app.util.db import DB
from app.controller.router import router
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse


def create_app():
    """
    앱 함수 실행
    :return:
    """

    app = FastAPI()

    DB().init_db()
    # 데이터 베이스 이니셜라이즈

    # 레디스 이니셜라이즈

    # 미들웨어 정의

    # 라우터 정의
    app.include_router(router)
    return app


app = create_app()


@app.get("/")
def health_check():
    return {"200": "ok"}


@app.exception_handler(401)
def except_unauthorized_handling(request: Request, exc: HTTPException):
    return RedirectResponse(url='/login')
