from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from app.service.login import LoginService



async def login_template(
        request: Request,
        service=Depends(LoginService)
):
    return await service.login_template(request)


async def login_post(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        service=Depends(LoginService)
):
    return await service.login_post(user_name=username, password=password, request=request)