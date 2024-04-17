from fastapi import APIRouter, Request, Depends
from app.service.attendee import AttendeeService
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone

templates = Jinja2Templates(directory="./template")

async def attendee_default(
        request: Request,
        service: Depends(AttendeeService)
):
    cur_date = datetime.now(timezone.utc)
    return
