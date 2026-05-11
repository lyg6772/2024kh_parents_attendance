import pytest

from app.dao.functions import (
    get_attendees,
    get_notices,
    get_password,
    save_attendees,
    save_notice,
)
from app.dao.tables import KyAtdcL, KyAtdcNotcL, KyUserL


class TestGetAttendees:
    async def test_empty_range(self, db_session):
        result = await get_attendees(db_session, "20260401", "20260430")
        assert result == []

    async def test_single_date_single_person(self, db_session):
        db_session.add(KyAtdcL(atdc_date="20260401", atde_name="김철수"))
        await db_session.commit()

        result = await get_attendees(db_session, "20260401", "20260430")
        assert len(result) == 1
        assert result[0]["atdc_date"] == "20260401"
        assert result[0]["atde_name"] == "김철수"

    async def test_single_date_multiple_people_sorted(self, db_session):
        db_session.add(KyAtdcL(atdc_date="20260401", atde_name="박영희"))
        db_session.add(KyAtdcL(atdc_date="20260401", atde_name="김철수"))
        await db_session.commit()

        result = await get_attendees(db_session, "20260401", "20260430")
        assert len(result) == 1
        assert result[0]["atde_name"] == "김철수,박영희"

    async def test_multiple_dates(self, db_session):
        db_session.add(KyAtdcL(atdc_date="20260401", atde_name="김철수"))
        db_session.add(KyAtdcL(atdc_date="20260402", atde_name="박영희"))
        await db_session.commit()

        result = await get_attendees(db_session, "20260401", "20260430")
        assert len(result) == 2
        dates = [r["atdc_date"] for r in result]
        assert "20260401" in dates
        assert "20260402" in dates

    async def test_range_filter_excludes_outside(self, db_session):
        db_session.add(KyAtdcL(atdc_date="20260331", atde_name="이전달"))
        db_session.add(KyAtdcL(atdc_date="20260401", atde_name="이번달"))
        db_session.add(KyAtdcL(atdc_date="20260501", atde_name="다음달"))
        await db_session.commit()

        result = await get_attendees(db_session, "20260401", "20260430")
        assert len(result) == 1
        assert result[0]["atde_name"] == "이번달"


class TestGetNotices:
    async def test_empty(self, db_session):
        result = await get_notices(db_session, "20260401", "20260430")
        assert result == []

    async def test_single_notice(self, db_session):
        db_session.add(KyAtdcNotcL(atdc_date="20260401", atdc_notice="체험학습"))
        await db_session.commit()

        result = await get_notices(db_session, "20260401", "20260430")
        assert len(result) == 1
        assert result[0]["atdc_date"] == "20260401"
        assert result[0]["atdc_notice"] == "체험학습"

    async def test_range_filter(self, db_session):
        db_session.add(KyAtdcNotcL(atdc_date="20260331", atdc_notice="이전"))
        db_session.add(KyAtdcNotcL(atdc_date="20260415", atdc_notice="이번달"))
        await db_session.commit()

        result = await get_notices(db_session, "20260401", "20260430")
        assert len(result) == 1
        assert result[0]["atdc_notice"] == "이번달"


class TestSaveAttendees:
    async def test_insert_new(self, db_session):
        await save_attendees(db_session, "20260401", ["김철수", "박영희"])

        result = await get_attendees(db_session, "20260401", "20260401")
        assert len(result) == 1
        assert result[0]["atde_name"] == "김철수,박영희"

    async def test_replace_existing(self, db_session):
        await save_attendees(db_session, "20260401", ["김철수"])
        await save_attendees(db_session, "20260401", ["박영희", "이민수"])

        result = await get_attendees(db_session, "20260401", "20260401")
        assert len(result) == 1
        assert "김철수" not in result[0]["atde_name"]
        assert result[0]["atde_name"] == "박영희,이민수"

    async def test_empty_list_clears(self, db_session):
        await save_attendees(db_session, "20260401", ["김철수"])
        await save_attendees(db_session, "20260401", [])

        result = await get_attendees(db_session, "20260401", "20260401")
        assert result == []


class TestSaveNotice:
    async def test_insert_new(self, db_session):
        await save_notice(db_session, "20260401", "체험학습")

        result = await get_notices(db_session, "20260401", "20260401")
        assert len(result) == 1
        assert result[0]["atdc_notice"] == "체험학습"

    async def test_replace_existing(self, db_session):
        await save_notice(db_session, "20260401", "체험학습")
        await save_notice(db_session, "20260401", "현장학습")

        result = await get_notices(db_session, "20260401", "20260401")
        assert len(result) == 1
        assert result[0]["atdc_notice"] == "현장학습"


class TestGetPassword:
    async def test_existing_user(self, db_session):
        db_session.add(KyUserL(user_id="admin", user_pw="hashed_pw"))
        await db_session.commit()

        result = await get_password(db_session, "admin")
        assert result == "hashed_pw"

    async def test_nonexistent_user(self, db_session):
        result = await get_password(db_session, "nobody")
        assert result is None
