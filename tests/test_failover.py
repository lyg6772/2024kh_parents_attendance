import pytest

from app.agent.llm import (
    FailoverAdapter,
    GroqAdapter,
    GroqUnavailableError,
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

    # Groq 후보 모델 전부 소진(모델 폐기 등) 시에도 Gemini로 전환
    async def test_fallback_on_groq_unavailable(self):
        primary = FakePrimary(error=GroqUnavailableError("all models dead"))
        fallback = FakeFallback(response=FINAL_RESPONSE)
        adapter = FailoverAdapter(primary, fallback)

        result = await adapter.chat([])
        assert fallback.called
        assert result.content == "응답"


def _fake_groq_error(cls, status_code):
    import httpx

    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=status_code, request=request)
    return cls("boom", response=response, body=None)


class _FakeCompletions:
    def __init__(self, side_effects):
        self._side_effects = list(side_effects)
        self.requested_models = []

    async def create(self, model, **kwargs):
        self.requested_models.append(model)
        effect = self._side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class _FakeGroqClient:
    def __init__(self, side_effects):
        self.chat = type("_Chat", (), {"completions": _FakeCompletions(side_effects)})()


def _groq_success(content="ok"):
    msg = type("_Msg", (), {"content": content, "tool_calls": None})()
    choice = type("_Choice", (), {"message": msg})()
    return type("_Resp", (), {"choices": [choice]})()


class TestGroqAdapterModelFallback:
    # 모델 폐기(404) 시 다음 후보 모델로 자동 전환
    async def test_moves_to_next_model_on_not_found(self):
        import groq

        not_found = _fake_groq_error(groq.NotFoundError, 404)
        adapter = GroqAdapter(api_key="fake", models=["dead-model", "live-model"])
        adapter._client = _FakeGroqClient([not_found, _groq_success("살아있음")])

        result = await adapter.chat([{"role": "user", "content": "hi"}])
        assert result.content == "살아있음"
        assert adapter._client.chat.completions.requested_models == ["dead-model", "live-model"]

    # 등록된 후보를 전부 소진하면 GroqUnavailableError
    async def test_raises_when_all_models_exhausted(self):
        import groq

        not_found = _fake_groq_error(groq.NotFoundError, 404)
        adapter = GroqAdapter(api_key="fake", models=["dead-1", "dead-2"])
        adapter._client = _FakeGroqClient([not_found, not_found])

        with pytest.raises(GroqUnavailableError):
            await adapter.chat([{"role": "user", "content": "hi"}])

    # 후보 목록이 비어있으면 원인이 드러나는 메시지로 즉시 실패
    async def test_raises_with_clear_message_when_no_models_configured(self):
        adapter = GroqAdapter(api_key="fake", models=[])
        adapter._client = _FakeGroqClient([])

        with pytest.raises(GroqUnavailableError, match="GROQ_MODEL"):
            await adapter.chat([{"role": "user", "content": "hi"}])

    # 401(키 오류)은 모델을 바꿔도 똑같이 실패하므로 다음 후보 시도 없이 즉시 전파
    async def test_does_not_retry_next_model_on_authentication_error(self):
        import groq

        auth_error = _fake_groq_error(groq.AuthenticationError, 401)
        adapter = GroqAdapter(api_key="fake", models=["model-a", "model-b"])
        adapter._client = _FakeGroqClient([auth_error, _groq_success("안 옴")])

        with pytest.raises(groq.AuthenticationError):
            await adapter.chat([{"role": "user", "content": "hi"}])
        assert adapter._client.chat.completions.requested_models == ["model-a"]
