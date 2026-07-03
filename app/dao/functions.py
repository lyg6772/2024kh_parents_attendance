from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.dao.tables import KyAtdcL, KyAtdcNotcL, KyUserL


async def get_attendees(session: AsyncSession, start_dt: str, end_dt: str) -> list[dict]:
    """날짜 범위 출석자 조회. LISTAGG 대신 Python에서 그룹핑."""
    stmt = (
        select(KyAtdcL)
        .where(KyAtdcL.atdc_date >= start_dt, KyAtdcL.atdc_date <= end_dt)
        .order_by(KyAtdcL.atdc_date, KyAtdcL.atde_name)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.atdc_date, []).append(row.atde_name)

    return [
        {"atdc_date": date, "atde_name": ",".join(names)}
        for date, names in grouped.items()
    ]


async def get_notices(session: AsyncSession, start_dt: str, end_dt: str) -> list[dict]:
    stmt = (
        select(KyAtdcNotcL)
        .where(KyAtdcNotcL.atdc_date >= start_dt, KyAtdcNotcL.atdc_date <= end_dt)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [{"atdc_date": r.atdc_date, "atdc_notice": r.atdc_notice} for r in rows]


async def save_attendees(session: AsyncSession, attendee_date: str, attendee_list: list[str]) -> None:
    await session.execute(delete(KyAtdcL).where(KyAtdcL.atdc_date == attendee_date))
    for name in attendee_list:
        session.add(KyAtdcL(atdc_date=attendee_date, atde_name=name))
    await session.commit()


async def save_notice(session: AsyncSession, attendee_date: str, notice: str) -> None:
    await session.execute(delete(KyAtdcNotcL).where(KyAtdcNotcL.atdc_date == attendee_date))
    session.add(KyAtdcNotcL(atdc_date=attendee_date, atdc_notice=notice))
    await session.commit()


async def get_password(session: AsyncSession, user_id: str) -> str | None:
    stmt = select(KyUserL.user_pw).where(KyUserL.user_id == user_id).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
