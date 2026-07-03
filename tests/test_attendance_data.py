import pytest

from app.dao.functions import get_attendees, save_attendees
from app.dao.tables import KyAtdcL, KyAtdcNotcL
from app.service.attendance_data import save_attendance
from app.agent.tools import build_registry


async def _seed_attendees(session, date: str, names: list[str]):
    for name in names:
        session.add(KyAtdcL(atdc_date=date, atde_name=name))
    await session.commit()


async def _seed_notice(session, date: str, text: str):
    session.add(KyAtdcNotcL(atdc_date=date, atdc_notice=text))
    await session.commit()


async def _get_names(session, date: str) -> list[str]:
    rows = await get_attendees(session, date, date)
    if not rows:
        return []
    return sorted(n.strip() for n in rows[0]["atde_name"].split(",") if n.strip())


class TestSaveAttendanceModeAdd:
    async def test_add_to_empty(self, db_session):
        await save_attendance(db_session, "20260507", attendee="김철수", mode="add")
        assert await _get_names(db_session, "20260507") == ["김철수"]

    async def test_add_to_existing(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수"])
        await save_attendance(db_session, "20260507", attendee="이영희", mode="add")
        assert await _get_names(db_session, "20260507") == ["김철수", "이영희"]

    async def test_add_multiple(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수"])
        await save_attendance(db_session, "20260507", attendee="이영희,박지민", mode="add")
        assert await _get_names(db_session, "20260507") == ["김철수", "박지민", "이영희"]

    async def test_add_duplicate_ignored(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수", "이영희"])
        await save_attendance(db_session, "20260507", attendee="김철수", mode="add")
        assert await _get_names(db_session, "20260507") == ["김철수", "이영희"]

    async def test_add_is_default_mode(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수"])
        await save_attendance(db_session, "20260507", attendee="이영희")
        assert await _get_names(db_session, "20260507") == ["김철수", "이영희"]


class TestSaveAttendanceModeRemove:
    async def test_remove_one(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수", "이영희", "박지민"])
        await save_attendance(db_session, "20260507", attendee="이영희", mode="remove")
        assert await _get_names(db_session, "20260507") == ["김철수", "박지민"]

    async def test_remove_multiple(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수", "이영희", "박지민"])
        await save_attendance(db_session, "20260507", attendee="김철수,박지민", mode="remove")
        assert await _get_names(db_session, "20260507") == ["이영희"]

    async def test_remove_nonexistent_no_error(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수"])
        await save_attendance(db_session, "20260507", attendee="이영희", mode="remove")
        assert await _get_names(db_session, "20260507") == ["김철수"]

    async def test_remove_all(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수", "이영희"])
        await save_attendance(db_session, "20260507", attendee="김철수,이영희", mode="remove")
        assert await _get_names(db_session, "20260507") == []

    async def test_remove_from_empty(self, db_session):
        await save_attendance(db_session, "20260507", attendee="김철수", mode="remove")
        assert await _get_names(db_session, "20260507") == []


class TestSaveAttendanceModeSet:
    async def test_set_replaces_entirely(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수", "이영희"])
        await save_attendance(db_session, "20260507", attendee="박지민", mode="set")
        assert await _get_names(db_session, "20260507") == ["박지민"]

    async def test_set_to_empty_clears(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수"])
        await save_attendance(db_session, "20260507", attendee="", mode="set")
        assert await _get_names(db_session, "20260507") == []

    async def test_set_on_empty_date(self, db_session):
        await save_attendance(db_session, "20260507", attendee="김철수,이영희", mode="set")
        assert await _get_names(db_session, "20260507") == ["김철수", "이영희"]


class TestSaveAttendanceEdgeCases:
    async def test_attendee_none_preserves_existing(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수"])
        await save_attendance(db_session, "20260507", attendee=None, mode="add")
        assert await _get_names(db_session, "20260507") == ["김철수"]

    async def test_notice_independent_of_attendee_mode(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수"])
        await save_attendance(db_session, "20260507", notice="비 옴", mode="remove")
        assert await _get_names(db_session, "20260507") == ["김철수"]

    async def test_whitespace_trimmed(self, db_session):
        await save_attendance(db_session, "20260507", attendee=" 김철수 , 이영희 ", mode="add")
        assert await _get_names(db_session, "20260507") == ["김철수", "이영희"]

    async def test_return_value_has_count(self, db_session):
        result = await save_attendance(db_session, "20260507", attendee="김철수,이영희", mode="add")
        assert result["saved"] is True
        assert result["count"] == 2


class TestPreviewSaveAttendance:
    async def _get_preview(self, db_session, **kw):
        registry = build_registry(db_session)
        tool = registry["save_attendance"]
        return await tool.preview(**kw)

    async def test_add_preview_shows_merged(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수"])
        preview = await self._get_preview(
            db_session, date="20260507", attendee="이영희", mode="add",
        )
        assert preview["date_display"] == "2026년 5월 7일"
        item = preview["items"][0]
        assert item["current"] == "김철수"
        assert "김철수" in item["new"]
        assert "이영희" in item["new"]

    async def test_remove_preview_shows_reduced(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수", "이영희", "박지민"])
        preview = await self._get_preview(
            db_session, date="20260507", attendee="이영희", mode="remove",
        )
        item = preview["items"][0]
        assert "이영희" not in item["new"]
        assert "김철수" in item["new"]
        assert "박지민" in item["new"]

    async def test_set_preview_shows_replacement(self, db_session):
        await _seed_attendees(db_session, "20260507", ["김철수", "이영희"])
        preview = await self._get_preview(
            db_session, date="20260507", attendee="박지민", mode="set",
        )
        item = preview["items"][0]
        assert item["new"] == "박지민"

    async def test_preview_empty_date(self, db_session):
        preview = await self._get_preview(
            db_session, date="20260507", attendee="김철수", mode="add",
        )
        item = preview["items"][0]
        assert item["current"] == "(없음)"
        assert item["new"] == "김철수"

    async def test_preview_notice_only(self, db_session):
        await _seed_notice(db_session, "20260507", "기존 메모")
        preview = await self._get_preview(
            db_session, date="20260507", notice="새 메모", mode="add",
        )
        assert len(preview["items"]) == 1
        assert preview["items"][0]["label"] == "특이사항"
        assert preview["items"][0]["current"] == "기존 메모"
        assert preview["items"][0]["new"] == "새 메모"

    async def test_preview_no_attendee_no_item(self, db_session):
        preview = await self._get_preview(
            db_session, date="20260507", mode="add",
        )
        assert preview["items"] == []
