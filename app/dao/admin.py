from app.util.db import DB
from fastapi import Depends
from sqlalchemy import text


class AdminAttendeeDao:
    def __init__(self, db_session=Depends(DB().get_db_session)):
        self.session = db_session

    async def get_attendee(self, start_dt: str, end_dt: str):
        query = text("""
        SELECT ATDC_DATE, GROUP_CONCAT(ATDE_NAME) AS ATDE_NAME
        FROM attendance.KY_ATDC_L 
        WHERE ATDC_DATE >= :start_dt
        AND ATDC_DATE <= :end_dt
        GROUP BY ATDC_DATE
        """)
        data = {"start_dt": start_dt, "end_dt": end_dt}
        async with self.session as session:
            result = await session.execute(query, data)
            response = result.mappings().all()
            return response

    async def get_notice(self, start_dt: str, end_dt: str):
        query = text("""
        SELECT ATDC_DATE, ATDC_NOTICE
        FROM attendance.KY_ATDC_NOTC_L 
        WHERE ATDC_DATE >= :start_dt
        AND ATDC_DATE <= :end_dt
        """)
        data = {"start_dt": start_dt, "end_dt": end_dt}
        async with self.session as session:
            result = await session.execute(query, data)
            response = result.mappings().all()
            return response

    async def insert_attendee(self, attendee_date, attendee_list):
        delete_query = text("""DELETE 
        FROM attendance.KY_ATDC_L
        WHERE ATDC_DATE = :attendee_date""")
        delete_data = {"attendee_date": attendee_date}
        insert_query = text("""
        INSERT INTO attendance.KY_ATDC_L(ATDC_DATE, ATDE_NAME) 
        values(:attendee_date, :attendee_name)""")
        insert_data = [{"attendee_date": attendee_date, "attendee_name": name} for name in attendee_list]
        async with self.session as session:
            await session.execute(delete_query, delete_data)
            await session.execute(insert_query, insert_data)
            await session.commit()

    async def insert_notice(self, attendee_date, notice):
        delete_query = text("""DELETE 
        FROM attendance.KY_ATDC_NOTC_L
        WHERE ATDC_DATE = :attendee_date""")
        delete_data = {"attendee_date": attendee_date}
        insert_query = text("""
        INSERT INTO attendance.KY_ATDC_NOTC_L(ATDC_DATE, ATDC_NOTICE) 
        values(:attendee_date, :notice)""")
        insert_data = {"attendee_date": attendee_date, "notice": notice}
        async with self.session as session:
            await session.execute(delete_query, delete_data)
            await session.execute(insert_query, insert_data)
            await session.commit()