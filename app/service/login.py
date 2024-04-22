from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from app.dao.login import LoginDao
from passlib.context import CryptContext

templates = Jinja2Templates(directory="./template")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginService:
    def __init__(self, dao: LoginDao = Depends(LoginDao)):
        self.dao = dao

    async def login_template(self, request: Request):
        return templates.TemplateResponse("login.html", {"request": request})

    async def login_post(self, user_name, password):
        hashed_password = await self.dao.get_password(user_name)
        if pwd_context.verify(password, hashed_password):
            # token 발행
            # redirect admin
            pass
        else:
            raise HTTPException(
                status_code=401,
                detail="Login Failure"
            )