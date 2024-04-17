from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext

templates = Jinja2Templates(directory="./template")


async def login_template(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


async def login_post(
        request: Request,
        username: str = Form(...),
        password: str = Form(...)
):
    return