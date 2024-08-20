from datetime import datetime, timedelta
from app.dao.admin import AdminAttendeeDao
from fastapi import Depends, Request
from dateutil.relativedelta import relativedelta
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response


templates = Jinja2Templates(directory="./app/template")


class AdminAttendeeService:
    def __init__(self, dao: AdminAttendeeDao = Depends(AdminAttendeeDao)):
        self.dao = dao

    async def get_attendee_table(self, request: Request, date_str):
        start_dt = datetime.strptime(f'{date_str}01', '%Y%m%d')
        end_dt = start_dt + relativedelta(months=1) - timedelta(days=1)
        before_month_str = datetime.strftime(start_dt - relativedelta(months=1), '%Y%m')
        after_month_str = datetime.strftime(start_dt + relativedelta(months=1), '%Y%m')
        attendance_raw = await self.dao.get_attendee(
            start_dt=start_dt.strftime('%Y%m%d'), end_dt=end_dt.strftime('%Y%m%d')
        )
        attendee_dict = dict()
        for attendance in attendance_raw:
            attendee_dict[attendance['ATDC_DATE']] = attendance['ATDE_NAME']
        notice_raw = await self.dao.get_notice(
            start_dt=start_dt.strftime('%Y%m%d'), end_dt=end_dt.strftime('%Y%m%d')
        )
        notice_dict = dict()
        for notice in notice_raw:
            notice_dict[notice['ATDC_DATE']] = notice['ATDC_NOTICE']
        starting_weekday = start_dt.isoweekday()
        num_days = (end_dt - start_dt).days + 1
        calendar = []
        week = []
        if starting_weekday != 7:
            for i in range(starting_weekday):
                week.append({"day": None, "attendee": '', 'notice': '', "date": None})
        for day in range(1, num_days + 1):
            cal_date = f"{date_str}{day:02d}"
            week.append(
                {"day": day, "attendee": attendee_dict.get(cal_date, ''), 'notice': notice_dict.get(cal_date, ''),
                 "date": cal_date})
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

    async def post_attendee(self, request:Request):
        json_data = await request.json()
        attendee_list = json_data.get('attendee', '').split(',')
        notice = json_data.get('notice', '')
        attendee_date = json_data.get('date')
        await self.dao.insert_attendee(attendee_date=attendee_date, attendee_list=attendee_list)
        await self.dao.insert_notice(attendee_date=attendee_date, notice=notice)

        return Response(status_code=200, content="OK")
