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
    return LLMResponse(content=content)


def make_tool_call(name: str, arguments: dict, call_id: str = "call_1") -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
    )


def make_tool_calls(*calls) -> LLMResponse:
    """한 응답에 여러 도구 호출을 담는다(병렬 tool calling). calls: (name, args) 또는 (name, args, id)."""
    tool_calls = []
    for i, c in enumerate(calls):
        name, args = c[0], c[1]
        call_id = c[2] if len(c) > 2 else f"call_{i + 1}"
        tool_calls.append(ToolCall(id=call_id, name=name, arguments=args))
    return LLMResponse(content=None, tool_calls=tool_calls)


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

    # 회귀 테스트: tool 에러 메시지 앞엔 반드시 매칭되는 assistant tool_calls가 와야 함
    # (없으면 OpenAI 호환 API가 다음 호출을 400으로 거부해 자가수정 루프가 죽는다)
    async def test_tool_error_message_paired_with_assistant_call(self):
        call_messages = []
        original_chat = MockLLM.chat

        class CaptureLLM(MockLLM):
            async def chat(self, messages, tools=None):
                call_messages.append(list(messages))
                return await original_chat(self, messages, tools)

        llm = CaptureLLM([
            make_tool_call("unknown_tool", {}, "call_1"),
            make_final("그 기능은 없습니다."),
        ])
        await run("없는 기능", [], TEST_REGISTRY, llm)

        retry_messages = call_messages[1]
        tool_msg_index = next(i for i, m in enumerate(retry_messages) if m.get("role") == "tool")
        preceding = retry_messages[tool_msg_index - 1]
        assert preceding["role"] == "assistant"
        assert preceding["tool_calls"][0]["id"] == "call_1"

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

    # 병렬 tool calling: 연속 저장 계획을 단 한 번의 LLM 호출로 확보
    async def test_parallel_writes_captured_in_one_llm_call(self):
        llm = MockLLM([
            make_tool_calls(
                ("save_attendance", {"date": "20260403", "attendee": "김철수"}, "c1"),
                ("save_attendance", {"date": "20260404", "attendee": "이영희"}, "c2"),
            ),
        ])
        result = await run("3일 김철수, 4일 이영희 추가", [], TEST_REGISTRY, llm)
        assert result.status == "pending_confirmation"
        assert result.pending["fn_name"] == "save_attendance"
        assert result.pending["kwargs"]["date"] == "20260403"
        assert len(result.pending["queue"]) == 1
        assert result.pending["queue"][0]["kwargs"]["date"] == "20260404"
        assert llm._call_count == 1  # 전체 계획을 한 번에 확보 (재진입 0회)

    # 병렬 tool calling: 저장 + 엑셀을 한 응답으로 받아 큐에 담음
    async def test_write_then_export_captured_in_one_llm_call(self):
        llm = MockLLM([
            make_tool_calls(
                ("save_attendance", {"date": "20260403", "attendee": "김철수"}, "c1"),
                ("export_excel", {"yyyymm": "202604"}, "c2"),
            ),
        ])
        result = await run("김철수 추가하고 엑셀 출력", [], TEST_REGISTRY, llm)
        assert result.status == "pending_confirmation"
        assert result.pending["fn_name"] == "save_attendance"
        assert result.pending["queue"][0]["fn_name"] == "export_excel"
        assert llm._call_count == 1

    # 병렬 READ: 한 응답의 여러 조회를 모두 실행하고 다음 턴에서 종합
    async def test_parallel_reads_execute_then_synthesize(self):
        llm = MockLLM([
            make_tool_calls(
                ("get_attendance", {"yyyymm": "202604"}, "c1"),
                ("get_attendance", {"yyyymm": "202605"}, "c2"),
            ),
            make_final("4월과 5월 현황입니다."),
        ])
        result = await run("4월 5월 비교", [], TEST_REGISTRY, llm)
        assert result.status == "done"
        assert "현황" in result.message
        assert llm._call_count == 2  # 조회 실행 후 종합 1회


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

    async def test_approved_empty_queue_no_llm_needed(self):
        """단순 저장: 큐가 비어 LLM 재호출 없이 즉시 done + date 기반 redirect"""
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260507", "attendee": "테스트", "mode": "add"},
            approved=True,
            registry=TEST_REGISTRY,
            queue=[],
        )
        assert result.status == "done"
        assert result.message == "저장했습니다."
        assert result.redirect == "/admin/attendee/202605"

    async def test_approved_drains_export_from_queue_without_llm(self):
        """'저장하고 엑셀도': save 승인 후 큐의 export_excel을 LLM 없이 실행 → export redirect"""
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260403", "attendee": "김철수"},
            approved=True,
            registry=TEST_REGISTRY,
            queue=[{"fn_name": "export_excel", "kwargs": {"yyyymm": "202604"}}],
        )
        assert result.status == "done"
        assert result.redirect == "/admin/attendee/export/202604"

    async def test_approved_stops_at_next_write_in_queue(self):
        """연속 저장: 3일 승인 후 큐의 4일 save가 WRITE라 다시 확인 요청(LLM 없이)"""
        result = await confirm(
            fn_name="save_attendance",
            kwargs={"date": "20260403", "attendee": "김철수"},
            approved=True,
            registry=TEST_REGISTRY,
            queue=[{"fn_name": "save_attendance", "kwargs": {"date": "20260404", "attendee": "이영희"}}],
        )
        assert result.status == "pending_confirmation"
        assert result.pending["fn_name"] == "save_attendance"
        assert result.pending["kwargs"]["date"] == "20260404"
        assert result.pending["queue"] == []

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
