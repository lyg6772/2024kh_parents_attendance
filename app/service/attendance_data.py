from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.functions import get_attendees, get_notices, save_attendees, save_notice
from app.service.attendance_logic import build_calendar_context, parse_date_range


async def get_attendance_data(session: AsyncSession, yyyymm: str) -> dict:
    dr = parse_date_range(yyyymm)
    attendees_raw = await get_attendees(session, dr.start_dt, dr.end_dt)
    notices_raw = await get_notices(session, dr.start_dt, dr.end_dt)
    cal = build_calendar_context(dr.year, dr.month)

    attendees = {r["atdc_date"]: r["atde_name"] for r in attendees_raw}
    notices = {r["atdc_date"]: r["atdc_notice"] for r in notices_raw}

    return {
        "year": cal.year,
        "month": cal.month,
        "weeks": cal.weeks,
        "prev_month": cal.prev_month,
        "next_month": cal.next_month,
        "attendees": attendees,
        "notices": notices,
    }


async def save_attendance(
    session: AsyncSession,
    date: str,
    attendee: str | None = None,
    notice: str | None = None,
) -> dict:
    saved_attendee_count = 0

    if attendee is not None:
        attendee_list = [name.strip() for name in attendee.split(",") if name.strip()]
        await save_attendees(session, date, attendee_list)
        saved_attendee_count = len(attendee_list)

    if notice is not None:
        await save_notice(session, date, notice)

    return {"saved": True, "date": date, "count": saved_attendee_count}


async def export_attendance(session: AsyncSession, yyyymm: str) -> dict:
    return {"redirect_url": f"/admin/attendee/export/{yyyymm}"}
