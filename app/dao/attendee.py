from app.util.db import DB

class AttendeeDao:
    def __init__(self):
        self.db = DB()

    async def get_attendee(self, start_dt: str, end_dt: str):
        query = """
        SELECT D.ATDC_DATE, GROUP_CONCAT(D.ATDC_NAME) AS ATDC_NAME, L.ATDC_NOTICE
        FROM attendance.KY_ATDC_L D 
        LEFT JOIN attendance.KY_ATDC_NOTC_L
        ON D.ATDC_DATE = L.ATDC_DATE
        WHERE D.ATDC_DATE >= %(start_dt)
        AND D.ATDC_DATE <= %(end_dt)
        GROUP BY D.ATDC_DATE
        """
        data = {"start_dt": start_dt, "end_dt": end_dt}
        with self.db.get_db_session() as session:
            result = session.execute(query, data)
            return result