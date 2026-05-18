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
    mode: str = "add",
) -> dict:
    saved_attendee_count = 0

    if attendee is not None:
        existing_raw = await get_attendees(session, date, date)
        existing_names = set()
        if existing_raw:
            existing_names = {n.strip() for n in existing_raw[0]["atde_name"].split(",") if n.strip()}

        input_names = {name.strip() for name in attendee.split(",") if name.strip()}

        if mode == "remove":
            result_names = existing_names - input_names
        elif mode == "set":
            result_names = input_names
        else:
            result_names = existing_names | input_names

        merged = sorted(result_names)
        await save_attendees(session, date, merged)
        saved_attendee_count = len(merged)

    if notice is not None:
        await save_notice(session, date, notice)

    return {"saved": True, "date": date, "count": saved_attendee_count}


async def export_attendance(session: AsyncSession, yyyymm: str) -> dict:
    return {"redirect_url": f"/admin/attendee/export/{yyyymm}"}
