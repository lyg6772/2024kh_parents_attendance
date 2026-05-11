import calendar
from datetime import datetime

from dateutil.relativedelta import relativedelta

from app.service.models import CalendarContext, DateRange


def parse_date_range(date_str: str) -> DateRange:
    """YYYYMM → DateRange. start_dt/end_dt는 YYYYMMDD 문자열."""
    year = int(date_str[:4])
    month = int(date_str[4:6])
    start_dt = f"{date_str}01"
    last_day = calendar.monthrange(year, month)[1]
    end_dt = f"{date_str}{last_day:02d}"
    return DateRange(start_dt=start_dt, end_dt=end_dt, year=year, month=month)


def build_calendar_context(year: int, month: int) -> CalendarContext:
    """일요일 시작 주별 배열 + prev/next month(YYYYMM)를 포함한 달력 컨텍스트."""
    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdayscalendar(year, month)

    base = datetime(year, month, 1)
    prev_dt = base - relativedelta(months=1)
    next_dt = base + relativedelta(months=1)

    return CalendarContext(
        year=year,
        month=month,
        weeks=weeks,
        prev_month=prev_dt.strftime("%Y%m"),
        next_month=next_dt.strftime("%Y%m"),
    )
