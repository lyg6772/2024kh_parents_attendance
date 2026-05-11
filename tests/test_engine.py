import pytest

from app.agent.engine import EngineResult, confirm, run
from app.agent.llm import LLMAdapter, LLMResponse, ToolCall
from app.agent.tools import (
    FunctionCategory,
    GetAttendanceArgs,
    SaveAttendanceArgs,
    ToolArgs,
    ToolDefinition,
    registry_to_tools_param,
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


async def _fake_write_handler(date: str, attendee: str, notice: str = "") -> dict:
    return {"saved": True, "date": date}


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

TEST_REGISTRY = {t.name: t for t in [READ_TOOL, WRITE_TOOL]}


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

    # P3-12: Confirmation 승인 시 실행
    async def test_confirm_approved(self):
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260403", "attendee": "김철수", "notice": ""},
            approved=True,
            registry=TEST_REGISTRY,
        )
        assert result.status == "done"
        assert "저장" in result.message

    # P3-13: Confirmation 거부 시 취소
    async def test_confirm_rejected(self):
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260403", "attendee": "김철수", "notice": ""},
            approved=False,
            registry=TEST_REGISTRY,
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
