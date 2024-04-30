from fastapi import APIRouter, Request, Depends, HTTPException
from app.service.admin import AdminAttendeeService
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
from app.util.auth import AuthHandler
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

templates = Jinja2Templates(directory="./template")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
auth_handler = AuthHandler()


async def get_current_user(request: Request):
    token = request.cookies.get("token", '')
    user_id = auth_handler.decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail='Could not validate credentials')
    return user_id


async def admin_attendee_get_default(
        request: Request,
        service=Depends(AdminAttendeeService),
        user: str = Depends(get_current_user)
):
    cur_date = datetime.now(timezone.utc)
    return await service.get_attendee_table(request=request, date_str=cur_date.strftime('%Y%m'))


async def admin_attendee_get_year_month(
        request: Request,
        cal_date: str,
        service=Depends(AdminAttendeeService),
        user: str = Depends(get_current_user)
):
    return await service.get_attendee_table(request=request, date_str=cal_date)