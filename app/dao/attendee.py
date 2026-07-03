from app.util.db import DB
from fastapi import Depends

from app.dao import functions as dao_fn


class AttendeeDao:
    def __init__(self, db_session=Depends(DB().get_db_session)):
        self.session = db_session

    async def get_attendee(self, start_dt: str, end_dt: str):
        async with self.session as session:
            return await dao_fn.get_attendees(session, start_dt, end_dt)

    async def get_notice(self, start_dt: str, end_dt: str):
        async with self.session as session:
            return await dao_fn.get_notices(session, start_dt, end_dt)
