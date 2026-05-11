import pytest
from pydantic import ValidationError

from app.agent.tools import (
    ExportExcelArgs,
    FunctionCategory,
    GetAttendanceArgs,
    REGISTRY,
    SaveAttendanceArgs,
    registry_to_tools_param,
)


class TestArgsSchema:
    # P3-01: model_json_schema()가 유효한 JSON Schema 반환
    def test_get_attendance_schema_has_required_field(self):
        schema = GetAttendanceArgs.model_json_schema()
        assert "yyyymm" in schema["properties"]
        assert "yyyymm" in schema["required"]

    def test_save_attendance_schema_has_required_fields(self):
        schema = SaveAttendanceArgs.model_json_schema()
        assert "date" in schema["required"]

    def test_save_attendance_notice_is_optional(self):
        schema = SaveAttendanceArgs.model_json_schema()
        assert "notice" not in schema.get("required", [])
        assert "attendee" not in schema.get("required", [])

    def test_export_excel_schema_has_required_field(self):
        schema = ExportExcelArgs.model_json_schema()
        assert "yyyymm" in schema["properties"]
        assert "yyyymm" in schema["required"]

    # P3-02: 유효한 인자로 Pydantic 모델 생성 성공
    def test_get_attendance_valid(self):
        args = GetAttendanceArgs(yyyymm="202604")
        assert args.yyyymm == "202604"

    def test_save_attendance_valid(self):
        args = SaveAttendanceArgs(date="20260403", attendee="김철수,이영희")
        assert args.date == "20260403"
        assert args.attendee == "김철수,이영희"
        assert args.notice is None

    def test_save_attendance_with_notice(self):
        args = SaveAttendanceArgs(date="20260403", attendee="김철수", notice="비 옴")
        assert args.notice == "비 옴"

    # P3-03: 잘못된 인자로 ValidationError 발생
    def test_save_attendance_missing_required(self):
        with pytest.raises(ValidationError):
            SaveAttendanceArgs()

    def test_save_attendance_date_only(self):
        args = SaveAttendanceArgs(date="20260403")
        assert args.date == "20260403"
        assert args.attendee is None
        assert args.notice is None

    def test_get_attendance_missing_required(self):
        with pytest.raises(ValidationError):
            GetAttendanceArgs()


class TestRegistry:
    # P3-04: REGISTRY에 모든 도구 등록 확인
    def test_registry_has_six_tools(self):
        assert len(REGISTRY) == 6

    def test_registry_tool_names(self):
        assert set(REGISTRY.keys()) == {"get_attendance", "save_attendance", "export_excel", "navigate_month", "logout", "get_help"}

    # P3-05: registry_to_tools_param이 OpenAI function calling 형식 반환
    def test_tools_param_format(self):
        params = registry_to_tools_param(REGISTRY)
        assert len(params) == 6
        for item in params:
            assert item["type"] == "function"
            assert "name" in item["function"]
            assert "description" in item["function"]
            assert "parameters" in item["function"]

    def test_tools_param_names_match_registry(self):
        params = registry_to_tools_param(REGISTRY)
        names = {item["function"]["name"] for item in params}
        assert names == set(REGISTRY.keys())

    # P3-06: READ/WRITE 카테고리 정확히 분류
    def test_get_attendance_is_read(self):
        assert REGISTRY["get_attendance"].category == FunctionCategory.READ

    def test_save_attendance_is_write(self):
        assert REGISTRY["save_attendance"].category == FunctionCategory.WRITE

    def test_export_excel_is_read(self):
        assert REGISTRY["export_excel"].category == FunctionCategory.READ
