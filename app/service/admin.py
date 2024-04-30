from datetime import datetime, timedelta
from app.dao.attendee import AttendeeDao
from fastapi import Depends
from dateutil.relativedelta import relativedelta
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(directory="./app/template")

class AdminAttendeeService:
    def __init__(self, dao: AttendeeDao = Depends(AttendeeDao)):
        self.dao = dao

    async def get_attendee_table(self, request, date_str):
        start_dt = datetime.strptime(f'{date_str}01', '%Y%m%d')
        end_dt = start_dt + relativedelta(months=1) - timedelta(days=1)
        before_month_str = datetime.strftime(start_dt - relativedelta(months=1), '%Y%m')
        after_month_str = datetime.strftime(start_dt + relativedelta(months=1), '%Y%m')
        attendance_info = await self.dao.get_attendee(
            start_dt=start_dt.strftime('%Y-%m-%d'), end_dt=end_dt.strftime('%Y-%m-%d')
        )
        starting_weekday = start_dt.isoweekday()
        num_days = (end_dt - start_dt).days + 1
        calendar = []
        week = []
        for i in range(starting_weekday):
            week.append({"day": None, "attendee": '', 'notice': '', "date": None})
        for day in range(1, num_days + 1):
            week.append({"day": day, "attendee": 'testtesttestestㅅㅅㅅㄷㄷㄴㄴㄴㅇㅀㅁㅇ', 'notice': 'testtesttest', "date": f"{date_str}{day:02d}"})
            if len(week) == 7:
                calendar.append(week)
                week = []
        if week:
            while len(week) < 7:
                week.append({"day": None, "attendee": '', 'notice': '', "date": None})
            calendar.append(week)

        return templates.TemplateResponse('./admin_attendee.html', context={
            "year": start_dt.year,
            "month": start_dt.month,
            "prev_month": before_month_str,
            "next_month": after_month_str,
            "calendar": calendar,
            "request": request
        })
