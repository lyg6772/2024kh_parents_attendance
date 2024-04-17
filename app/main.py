from typing import Optional
import aiomysql
import uvicorn
from fastapi import FastAPI
from app.util.db import DB
from app.controller.router import router


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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)