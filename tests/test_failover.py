import pytest

from app.agent.llm import (
    FailoverAdapter,
    LLMAdapter,
    LLMResponse,
    RateLimitError,
    _openai_messages_to_gemini,
)


class TestGeminiMessageConversion:
    # 회귀: function_response.name이 하드코딩 "tool"이 아니라 원래 도구 이름과 일치해야 함
    def test_function_response_name_matches_tool_call(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "6월 조회"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "get_attendance", "arguments": '{"yyyymm":"202604"}'}}
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'},
        ]
        contents = _openai_messages_to_gemini(messages)
        responses = [p["function_response"] for c in contents for p in c["parts"] if "function_response" in p]
        assert len(responses) == 1
        assert responses[0]["name"] == "get_attendance"  # not "tool"
        assert responses[0]["response"] == {"ok": True}

    # 병렬 호출도 전부 보존 (tool_calls[0] 잘림 없음)
    def test_preserves_all_parallel_tool_calls(self):
        messages = [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "save_attendance", "arguments": "{}"}},
                {"id": "c2", "type": "function", "function": {"name": "export_excel", "arguments": "{}"}},
            ]},
        ]
        contents = _openai_messages_to_gemini(messages)
        calls = [p["function_call"]["name"] for c in contents for p in c["parts"] if "function_call" in p]
        assert calls == ["save_attendance", "export_excel"]


class FakePrimary(LLMAdapter):
    def __init__(self, response: LLMResponse | None = None, error: Exception | None = None):
        self._response = response
        self._error = error
        self.called = False

    async def chat(self, messages, tools=None) -> LLMResponse:
        self.called = True
        if self._error:
            raise self._error
        return self._response


class FakeFallback(LLMAdapter):
    def __init__(self, response: LLMResponse | None = None, error: Exception | None = None):
        self._response = response
        self._error = error
        self.called = False

    async def chat(self, messages, tools=None) -> LLMResponse:
        self.called = True
        if self._error:
            raise self._error
        return self._response


FINAL_RESPONSE = LLMResponse(content="응답")


class TestFailoverAdapter:
    # P3-20: Primary 정상 시 Primary 사용
    async def test_primary_success(self):
        primary = FakePrimary(response=FINAL_RESPONSE)
        fallback = FakeFallback(response=FINAL_RESPONSE)
        adapter = FailoverAdapter(primary, fallback)

        result = await adapter.chat([])
        assert primary.called
        assert not fallback.called
        assert result.content == "응답"

    # P3-21: Primary RateLimit 시 Fallback 전환
    async def test_fallback_on_rate_limit(self):
        primary = FakePrimary(error=RateLimitError())
        fallback = FakeFallback(response=FINAL_RESPONSE)
        adapter = FailoverAdapter(primary, fallback)

        result = await adapter.chat([])
        assert primary.called
        assert fallback.called
        assert result.content == "응답"

    # P3-22: Fallback도 실패 시 에러 전파
    async def test_both_fail(self):
        primary = FakePrimary(error=RateLimitError())
        fallback = FakeFallback(error=RuntimeError("fallback도 실패"))
        adapter = FailoverAdapter(primary, fallback)

        with pytest.raises(RuntimeError, match="fallback도 실패"):
            await adapter.chat([])
