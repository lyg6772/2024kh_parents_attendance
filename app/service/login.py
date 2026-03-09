from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from passlib.context import CryptContext
from app.dao.login import LoginDao
from app.util.auth import AuthHandler

templates = Jinja2Templates(directory="./app/template")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
auth = AuthHandler()


class LoginService:
    def __init__(self, dao: LoginDao = Depends(LoginDao)):
        self.dao = dao

    async def login_template(self, request: Request):
        # 이미 토큰이 있으면 관리자 페이지로 바로 이동
        token = request.cookies.get("token", '')
        if token:
            try:
                user_id = auth.decode_token(token)
                if user_id:
                    return RedirectResponse(url='/admin/attendee', status_code=302)
            except:
                pass

        return templates.TemplateResponse("login.html", {"request": request})

    async def login_post(self, user_name, password, request):
        hashed_password = await self.dao.get_password(user_name)
        if pwd_context.verify(password, hashed_password):
            # token 발행
            encoded_token = auth.encode_token(user_id=user_name)
            res = JSONResponse(content={"token": encoded_token})
            res.set_cookie(key="token", value=encoded_token)
            return res
        else:
            raise HTTPException(
                status_code=401,
                detail="Login Failure"
            )