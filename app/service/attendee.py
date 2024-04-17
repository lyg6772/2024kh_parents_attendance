from datetime import datetime, timedelta
from app.dao.attendee import AttendeeDao
from fastapi import Depends
from dateutil import relativedelta

class AttendeeService:
    def __init__(self, dao: AttendeeDao = Depends(AttendeeDao)):
        self.dao = dao

    async def get_attendee_table(self, date_str):
        start_dt = datetime.strptime(f'{date_str}01', '%Y%m%d')
        end_dt = start_dt + relativedelta(months=1) - timedelta(days=1)
        before_month_str = datetime.strftime(start_dt - relativedelta(months=1), '%Y%m')
        after_month_str = datetime.strftime(start_dt - relativedelta(months=1), '%Y%m')
        attendance_info = self.dao.get_attendee(start_dt=start_dt, end_dt=end_dt)
        cur_date = start_dt

        while cur_date <= end_dt:

            pass