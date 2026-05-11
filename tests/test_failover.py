import pytest

from app.agent.llm import (
    FailoverAdapter,
    LLMAdapter,
    LLMResponse,
    RateLimitError,
)


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


FINAL_RESPONSE = LLMResponse(is_final=True, content="응답", tool_call=None)


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
