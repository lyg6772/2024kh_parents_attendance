from app.service.attendance_logic import (
    build_calendar_context,
    parse_date_range,
)
from app.service.models import AttendeeRow, AttendanceData, CalendarContext, DateRange, NoticeRow


class TestParseDateRange:
    # P2-01: YYYYMM → DateRange
    def test_basic_conversion(self):
        result = parse_date_range("202604")
        assert isinstance(result, DateRange)
        assert result.start_dt == "20260401"
        assert result.end_dt == "20260430"
        assert result.year == 2026
        assert result.month == 4

    # P2-02: 월말 날짜 정확히 계산 (28/29/30/31)
    def test_february_non_leap(self):
        assert parse_date_range("202602").end_dt == "20260228"

    def test_february_leap_year(self):
        assert parse_date_range("202802").end_dt == "20280229"

    def test_january_31_days(self):
        assert parse_date_range("202601").end_dt == "20260131"

    def test_june_30_days(self):
        assert parse_date_range("202606").end_dt == "20260630"


class TestBuildCalendarContext:
    # P2-03: 해당 월의 주별 날짜 배열 반환, 일요일 시작 (firstweekday=6)
    def test_returns_calendar_context(self):
        ctx = build_calendar_context(2026, 4)
        assert isinstance(ctx, CalendarContext)

    def test_weeks_structure(self):
        ctx = build_calendar_context(2026, 4)
        assert isinstance(ctx.weeks, list)
        assert all(len(week) == 7 for week in ctx.weeks)

    def test_sunday_start(self):
        ctx = build_calendar_context(2026, 4)
        # 2026-04-01 is Wednesday → first week should have 0s for Sun/Mon/Tue
        first_week = ctx.weeks[0]
        assert first_week[0] == 0  # Sunday
        assert first_week[1] == 0  # Monday
        assert first_week[2] == 0  # Tuesday
        assert first_week[3] == 1  # Wednesday = 1st

    def test_all_days_present(self):
        ctx = build_calendar_context(2026, 4)
        all_days = [d for week in ctx.weeks for d in week if d != 0]
        assert all_days == list(range(1, 31))

    # P2-04: prev/next month 정보 포함 (연도 넘김 처리)
    def test_prev_next_month(self):
        ctx = build_calendar_context(2026, 4)
        assert ctx.prev_month == "202603"
        assert ctx.next_month == "202605"

    def test_december_year_boundary(self):
        ctx = build_calendar_context(2026, 12)
        assert ctx.prev_month == "202611"
        assert ctx.next_month == "202701"

    def test_january_year_boundary(self):
        ctx = build_calendar_context(2026, 1)
        assert ctx.prev_month == "202512"
        assert ctx.next_month == "202602"

    def test_year_month_in_context(self):
        ctx = build_calendar_context(2026, 4)
        assert ctx.year == 2026
        assert ctx.month == 4


class TestAttendeeRow:
    def test_lowercase_columns(self):
        row = AttendeeRow.model_validate({"atdc_date": "20260401", "atde_name": "김철수"})
        assert row.atdc_date == "20260401"
        assert row.atde_name == "김철수"

    def test_uppercase_columns(self):
        row = AttendeeRow.model_validate({"ATDC_DATE": "20260401", "ATDE_NAME": "이영희"})
        assert row.atdc_date == "20260401"
        assert row.atde_name == "이영희"

    def test_missing_name_defaults_empty(self):
        row = AttendeeRow.model_validate({"ATDC_DATE": "20260401"})
        assert row.atde_name == ""


class TestNoticeRow:
    def test_lowercase_columns(self):
        row = NoticeRow.model_validate({"atdc_date": "20260401", "atdc_notice": "비 옴"})
        assert row.atdc_date == "20260401"
        assert row.atdc_notice == "비 옴"

    def test_uppercase_columns(self):
        row = NoticeRow.model_validate({"ATDC_DATE": "20260401", "ATDC_NOTICE": "체험학습"})
        assert row.atdc_date == "20260401"
        assert row.atdc_notice == "체험학습"

    def test_missing_notice_defaults_empty(self):
        row = NoticeRow.model_validate({"atdc_date": "20260401"})
        assert row.atdc_notice == ""


class TestAttendanceData:
    def test_from_calendar_context(self):
        ctx = build_calendar_context(2026, 4)
        data = AttendanceData(
            **ctx.model_dump(),
            attendees={"20260401": "김철수"},
            notices={"20260401": "비 옴"},
        )
        assert data.year == 2026
        assert data.attendees["20260401"] == "김철수"
        assert data.notices["20260401"] == "비 옴"

    def test_empty_attendees_and_notices(self):
        ctx = build_calendar_context(2026, 4)
        data = AttendanceData(**ctx.model_dump())
        assert data.attendees == {}
        assert data.notices == {}
