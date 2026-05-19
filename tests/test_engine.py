import pytest

from app.agent.engine import EngineResult, confirm, run
from app.agent.llm import LLMAdapter, LLMResponse, ToolCall
from app.agent.tools import (
    ExportExcelArgs,
    FunctionCategory,
    GetAttendanceArgs,
    SaveAttendanceArgs,
    ToolArgs,
    ToolDefinition,
)


class MockLLM(LLMAdapter):

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self._call_count = 0

    async def chat(self, messages, tools=None) -> LLMResponse:
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp


def make_final(content: str) -> LLMResponse:
    return LLMResponse(is_final=True, content=content, tool_call=None)


def make_tool_call(name: str, arguments: dict, call_id: str = "call_1") -> LLMResponse:
    return LLMResponse(
        is_final=False,
        content=None,
        tool_call=ToolCall(id=call_id, name=name, arguments=arguments),
    )


async def _fake_read_handler(yyyymm: str) -> dict:
    return {"attendees": {"20260401": "김철수"}, "notices": {}}


async def _fake_write_handler(**kwargs) -> dict:
    return {"saved": True, "date": kwargs.get("date", "")}


async def _fake_export_handler(yyyymm: str) -> dict:
    return {"redirect_url": f"/admin/attendee/export/{yyyymm}"}


READ_TOOL = ToolDefinition(
    name="get_attendance",
    summary="조회",
    description="출석 조회",
    category=FunctionCategory.READ,
    args_schema=GetAttendanceArgs,
    handler=_fake_read_handler,
)

WRITE_TOOL = ToolDefinition(
    name="save_attendance",
    summary="저장",
    description="출석 저장",
    category=FunctionCategory.WRITE,
    args_schema=SaveAttendanceArgs,
    handler=_fake_write_handler,
)

EXPORT_TOOL = ToolDefinition(
    name="export_excel",
    summary="엑셀 다운로드",
    description="출석부 엑셀 다운로드",
    category=FunctionCategory.READ,
    args_schema=ExportExcelArgs,
    handler=_fake_export_handler,
)

TEST_REGISTRY = {t.name: t for t in [READ_TOOL, WRITE_TOOL, EXPORT_TOOL]}


class TestEngineRun:
    # P3-10: 단순 READ 요청 처리
    async def test_read_then_final(self):
        llm = MockLLM([
            make_tool_call("get_attendance", {"yyyymm": "202604"}),
            make_final("4월 출석 현황입니다."),
        ])
        result = await run("4월 출석 알려줘", [], TEST_REGISTRY, llm)
        assert result.status == "done"
        assert "4월" in result.message

    # P3-11: WRITE 요청 시 Confirmation Gate 작동
    async def test_write_triggers_confirmation(self):
        llm = MockLLM([
            make_tool_call("save_attendance", {"date": "20260403", "attendee": "김철수,이영희"}),
        ])
        result = await run("4월 3일 저장해줘", [], TEST_REGISTRY, llm)
        assert result.status == "pending_confirmation"
        assert result.pending is not None
        assert result.pending["fn_name"] == "save_attendance"
        assert result.pending["kwargs"]["date"] == "20260403"

    # P3-12: Confirmation 승인 후 후속 작업 없이 완료
    async def test_confirm_approved(self):
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260403", "attendee": "김철수", "notice": ""},
            approved=True,
            registry=TEST_REGISTRY,
        )
        assert result.status == "done"
        assert result.message == "저장했습니다."
        assert result.redirect == "/admin/attendee/202604"

    # P3-13: Confirmation 거부 시 취소 (루프 재진입 안 함)
    async def test_confirm_rejected(self):
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260403", "attendee": "김철수", "notice": ""},
            approved=False,
            registry=TEST_REGISTRY,
            message="참석자 추가해줘",
            history=[],
            llm=None,
        )
        assert result.status == "done"
        assert "취소" in result.message

    # P3-14: MAX_TURNS 초과 시 강제 종료
    async def test_max_turns_exceeded(self):
        llm = MockLLM([
            make_tool_call("get_attendance", {"yyyymm": "202604"}, f"call_{i}")
            for i in range(6)
        ])
        result = await run("계속 조회해", [], TEST_REGISTRY, llm)
        assert result.status == "error"
        assert "한도" in result.message

    # P3-15: 존재하지 않는 도구 호출 시 에러 후 루프 계속
    async def test_unknown_tool_then_final(self):
        llm = MockLLM([
            make_tool_call("unknown_tool", {}),
            make_final("그 기능은 없습니다."),
        ])
        result = await run("없는 기능", [], TEST_REGISTRY, llm)
        assert result.status == "done"
        assert llm._call_count == 2

    # P3-16: 인자 검증 실패 시 에러 후 루프 계속
    async def test_validation_error_then_final(self):
        llm = MockLLM([
            make_tool_call("save_attendance", {}),
            make_final("인자가 부족합니다."),
        ])
        result = await run("저장해줘", [], TEST_REGISTRY, llm)
        assert result.status == "done"
        assert llm._call_count == 2

    # P3-17: 멀티스텝 — 조회 후 저장
    async def test_read_then_write(self):
        llm = MockLLM([
            make_tool_call("get_attendance", {"yyyymm": "202604"}, "call_1"),
            make_tool_call("save_attendance", {"date": "20260403", "attendee": "김철수"}, "call_2"),
        ])
        result = await run("조회 후 저장", [], TEST_REGISTRY, llm)
        assert result.status == "pending_confirmation"
        assert result.pending["fn_name"] == "save_attendance"

    # P3-18: LLM이 도구 호출 없이 바로 응답
    async def test_direct_final_response(self):
        llm = MockLLM([
            make_final("이 기능은 지원하지 않습니다."),
        ])
        result = await run("날씨 알려줘", [], TEST_REGISTRY, llm)
        assert result.status == "done"
        assert "지원" in result.message


class TestConfirm:
    async def test_approved_returns_redirect_with_date_month(self):
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260403", "attendee": "김철수"},
            approved=True,
            registry=TEST_REGISTRY,
        )
        assert result.status == "done"
        assert result.message == "저장했습니다."
        assert result.redirect == "/admin/attendee/202604"

    async def test_approved_no_date_field_no_redirect(self):
        result = await confirm(
            fn_name="export_excel",
            kwargs={"yyyymm": "202604"},
            approved=True,
            registry=TEST_REGISTRY,
        )
        assert result.status == "done"
        assert result.redirect is None

    async def test_rejected_no_handler_call(self):
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260403", "attendee": "김철수"},
            approved=False,
            registry=TEST_REGISTRY,
        )
        assert result.status == "done"
        assert "취소" in result.message
        assert result.redirect is None

    async def test_approved_does_not_call_llm(self):
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260507", "attendee": "테스트", "mode": "add"},
            approved=True,
            registry=TEST_REGISTRY,
            message="원래 메시지",
            history=[],
            llm=MockLLM([make_final("이건 호출되면 안됨")]),
        )
        assert result.status == "done"
        assert result.redirect == "/admin/attendee/202605"

    async def test_approved_handler_exception_returns_error(self):
        """confirm 승인 시 handler가 예외 던지면 error 반환 (500 아님)"""

        async def _exploding_handler(**kwargs):
            raise RuntimeError("DB connection lost")

        error_registry = {
            "save_attendance": ToolDefinition(
                name="save_attendance",
                summary="저장",
                description="저장",
                category=FunctionCategory.WRITE,
                args_schema=SaveAttendanceArgs,
                handler=_exploding_handler,
            ),
        }
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260507", "attendee": "김철수"},
            approved=True,
            registry=error_registry,
        )
        assert result.status == "error"
        assert "저장 실패" in result.message


class TestEngineRedirect:
    """engine.run()에서 READ handler가 redirect_url 반환하는 경로"""

    async def test_redirect_url_in_result(self):
        llm = MockLLM([
            make_tool_call("export_excel", {"yyyymm": "202604"}),
        ])
        result = await run("엑셀 다운로드", [], TEST_REGISTRY, llm)
        assert result.status == "done"
        assert result.redirect == "/admin/attendee/export/202604"

    async def test_navigate_month_redirect(self):
        navigate_tool = ToolDefinition(
            name="navigate_month",
            summary="이동",
            description="월 이동",
            category=FunctionCategory.READ,
            args_schema=type("NavArgs", (ToolArgs,), {"__annotations__": {"yyyymm": str}}),
            handler=lambda **kw: _make_coro({"redirect_url": f"/admin/attendee/{kw['yyyymm']}"}),
        )
        registry = {**TEST_REGISTRY, "navigate_month": navigate_tool}
        llm = MockLLM([
            make_tool_call("navigate_month", {"yyyymm": "202605"}),
        ])
        result = await run("다음 달", [], registry, llm)
        assert result.status == "done"
        assert result.redirect == "/admin/attendee/202605"


class TestEngineHandlerError:
    """engine.run()에서 READ handler가 예외 던지면 에러 메시지 후 루프 계속"""

    async def test_handler_exception_then_final(self):
        async def _exploding_read(yyyymm: str):
            raise RuntimeError("DB timeout")

        error_tool = ToolDefinition(
            name="get_attendance",
            summary="조회",
            description="출석 조회",
            category=FunctionCategory.READ,
            args_schema=GetAttendanceArgs,
            handler=_exploding_read,
        )
        registry = {**TEST_REGISTRY, "get_attendance": error_tool}
        llm = MockLLM([
            make_tool_call("get_attendance", {"yyyymm": "202604"}),
            make_final("DB 오류가 발생했습니다."),
        ])
        result = await run("출석 조회", [], registry, llm)
        assert result.status == "done"
        assert llm._call_count == 2

    async def test_handler_exception_message_contains_error(self):
        """에러 메시지가 tool result로 LLM에 전달됨을 확인"""

        async def _exploding_read(yyyymm: str):
            raise ValueError("invalid month format")

        error_tool = ToolDefinition(
            name="get_attendance",
            summary="조회",
            description="출석 조회",
            category=FunctionCategory.READ,
            args_schema=GetAttendanceArgs,
            handler=_exploding_read,
        )
        registry = {**TEST_REGISTRY, "get_attendance": error_tool}

        call_messages = []
        original_chat = MockLLM.chat

        class CaptureLLM(MockLLM):
            async def chat(self, messages, tools=None):
                call_messages.append(messages)
                return await original_chat(self, messages, tools)

        llm = CaptureLLM([
            make_tool_call("get_attendance", {"yyyymm": "202604"}),
            make_final("오류 발생"),
        ])
        await run("출석 조회", [], registry, llm)
        last_messages = call_messages[-1]
        tool_msgs = [m for m in last_messages if m.get("role") == "tool"]
        assert any("invalid month format" in m["content"] for m in tool_msgs)


async def _make_coro(val):
    return val
