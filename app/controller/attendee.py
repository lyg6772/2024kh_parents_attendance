from fastapi import APIRouter, Request, Depends
from app.service.attendee import AttendeeService
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone

templates = Jinja2Templates(directory="./template")


async def attendee_get_default(
        request: Request,
        service=Depends(AttendeeService)
):
    cur_date = datetime.now(timezone.utc)
    return await service.get_attendee_table(request=request, date_str=cur_date.strftime('%Y%m'))


async def attendee_get_year_month(
        request: Request,
        cal_date: str,
        service=Depends(AttendeeService)
):
    return await service.get_attendee_table(request=request, date_str=cal_date)