from app.util.db import DB
from fastapi import Depends
from sqlalchemy import text


class AttendeeDao:
    def __init__(self, db_session=Depends(DB().get_db_session)):
        self.session = db_session

    async def get_attendee(self, start_dt: str, end_dt: str):
        query = text("""
        SELECT D.ATDC_DATE, GROUP_CONCAT(D.ATDE_NAME) AS ATDE_NAME, L.ATDC_NOTICE
        FROM attendance.KY_ATDC_L D 
        LEFT JOIN attendance.KY_ATDC_NOTC_L L
        ON D.ATDC_DATE = L.ATDC_DATE
        WHERE D.ATDC_DATE >= :start_dt
        AND D.ATDC_DATE <= :end_dt
        GROUP BY D.ATDC_DATE
        """)
        data = {"start_dt": start_dt, "end_dt": end_dt}
        async with self.session as session:
            result = await session.execute(query, {"start_dt": start_dt, "end_dt": end_dt})
            return result.fetchall()