from app.util.db import DB
from fastapi import Depends

from app.dao import functions as dao_fn


class AdminAttendeeDao:
    def __init__(self, db_session=Depends(DB().get_db_session)):
        self.session = db_session

    async def get_attendee(self, start_dt: str, end_dt: str):
        async with self.session as session:
            return await dao_fn.get_attendees(session, start_dt, end_dt)

    async def get_notice(self, start_dt: str, end_dt: str):
        async with self.session as session:
            return await dao_fn.get_notices(session, start_dt, end_dt)

    async def insert_attendee(self, attendee_date, attendee_list):
        async with self.session as session:
            await dao_fn.save_attendees(session, attendee_date, attendee_list)

    async def insert_notice(self, attendee_date, notice):
        async with self.session as session:
            await dao_fn.save_notice(session, attendee_date, notice)
