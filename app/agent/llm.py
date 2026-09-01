import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app import config

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # tool_calls가 비면 최종 응답, 있으면 (하나 이상의) 도구 호출.


class LLMAdapter(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse: ...


class RateLimitError(Exception):
    pass


class GroqUnavailableError(Exception):
    """등록된 Groq 후보 모델을 전부 시도했지만 다 실패했다."""


class GroqAdapter(LLMAdapter):
    def __init__(self, api_key: str = "", models: list[str] | None = None):
        from groq import AsyncGroq

        self._client = AsyncGroq(api_key=api_key or config.GROQ_API_KEY)
        self._models = config.GROQ_MODELS if models is None else models

    async def chat(self, messages, tools=None) -> LLMResponse:
        from groq import APIStatusError as GroqAPIStatusError

        kwargs: dict = {"messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if not self._models:
            raise GroqUnavailableError("GROQ_MODEL이 설정되지 않았습니다 (후보 모델 없음)")

        last_err: Exception | None = None
        for model in self._models:
            try:
                resp = await self._client.chat.completions.create(model=model, **kwargs)
            except GroqAPIStatusError as e:
                # 401/403(키·권한)과 400(요청 자체 오류 — 잘못된 tool schema 등)은 모델을
                # 바꿔도 똑같이 실패한다. 근본 원인을 숨기지 않도록 즉시 올린다.
                # 모델 자체 문제(폐기 등, 실측상 404)와 일시적 문제(429/5xx)만 다음 후보로.
                if e.status_code in (400, 401, 403):
                    raise
                logger.warning("Groq model %s unavailable (%s), trying next candidate", model, e)
                last_err = e
                continue

            msg = resp.choices[0].message

            if msg.tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=(
                            json.loads(tc.function.arguments)
                            if isinstance(tc.function.arguments, str)
                            else tc.function.arguments
                        ),
                    )
                    for tc in msg.tool_calls
                ]
                return LLMResponse(content=msg.content, tool_calls=tool_calls)

            return LLMResponse(content=msg.content)

        raise GroqUnavailableError(str(last_err)) from last_err


class GeminiAdapter(LLMAdapter):
    def __init__(self, api_key: str = "", model: str = ""):
        from google import genai

        self._client = genai.Client(api_key=api_key or config.GEMINI_API_KEY)
        self._model = model or config.GEMINI_MODEL

    async def chat(self, messages, tools=None) -> LLMResponse:
        from google.genai import types

        contents = _openai_messages_to_gemini(messages)
        gemini_tools = _openai_tools_to_gemini(tools) if tools else None

        config_kwargs: dict = {}
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools

        resp = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
        )

        # 안전필터/프롬프트 차단 시 candidates가 비거나 content가 None일 수 있다.
        if not resp.candidates:
            return LLMResponse(content="응답을 생성할 수 없습니다. 잠시 후 다시 시도해주세요.")
        candidate = resp.candidates[0]
        parts = (candidate.content.parts if candidate.content else None) or []

        tool_calls = []
        text = None
        for i, part in enumerate(parts):
            fc = getattr(part, "function_call", None)
            if fc:
                # 인덱스를 id에 포함 — 같은 함수를 병렬로 두 번 부르면 이름만으론 id가 충돌한다.
                tool_calls.append(
                    ToolCall(
                        id=f"gemini_{i}_{fc.name}",
                        name=fc.name or "",
                        arguments=dict(fc.args) if fc.args else {},
                    )
                )
            elif getattr(part, "text", None):
                text = part.text

        if tool_calls:
            return LLMResponse(content=None, tool_calls=tool_calls)

        # content가 None(안전차단 등)이면 빈 말풍선 대신 안내 문구
        if text is None:
            return LLMResponse(content="응답을 생성할 수 없습니다. 잠시 후 다시 시도해주세요.")
        return LLMResponse(content=text)


def _openai_messages_to_gemini(messages: list[dict]) -> list[dict]:
    contents = []
    system_parts = []
    # Gemini는 function_response.name이 앞선 function_call.name과 일치해야 한다.
    # tool 메시지엔 이름이 없고 tool_call_id만 있으므로, assistant 턴에서 id→name을 모아둔다.
    tool_id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if role == "system":
            system_parts.append(content)
        elif role == "user":
            prefix = "\n".join(system_parts) + "\n\n" if system_parts else ""
            system_parts = []
            contents.append({"role": "user", "parts": [{"text": prefix + (content or "")}]})
        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                parts = []
                for tc in tool_calls:
                    fn = tc["function"]
                    args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                    tool_id_to_name[tc["id"]] = fn["name"]
                    parts.append({"function_call": {"name": fn["name"], "args": args}})
                contents.append({"role": "model", "parts": parts})
            else:
                contents.append({"role": "model", "parts": [{"text": content or ""}]})
        elif role == "tool":
            tool_content = msg.get("content", "{}")
            result = json.loads(tool_content) if isinstance(tool_content, str) else tool_content
            fn_name = tool_id_to_name.get(msg.get("tool_call_id", ""), "tool")
            contents.append({
                "role": "user",
                "parts": [{"function_response": {"name": fn_name, "response": result}}],
            })

    return contents


def _strip_unsupported_keys(schema: dict) -> dict:
    """Gemini function declaration에서 지원하지 않는 키를 재귀적으로 제거한다.
    pattern도 제외 — Gemini 선언 스키마가 거부할 수 있고, 실제 검증은 pydantic이 하므로
    Gemini에 힌트가 없어도 자가수정 루프는 그대로 작동한다."""
    unsupported = {"examples", "default", "$defs", "title", "pattern"}
    cleaned: dict = {}
    for k, v in schema.items():
        if k in unsupported:
            continue
        if isinstance(v, dict):
            cleaned[k] = _strip_unsupported_keys(v)
        else:
            cleaned[k] = v
    return cleaned


def _openai_tools_to_gemini(tools: list[dict]) -> list[dict]:
    declarations = []
    for tool in tools:
        fn = tool["function"]
        params = _strip_unsupported_keys(fn.get("parameters", {}))
        declarations.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": params,
        })
    return [{"function_declarations": declarations}]


class FailoverAdapter(LLMAdapter):
    def __init__(self, primary: LLMAdapter, fallback: LLMAdapter):
        self.primary = primary
        self.fallback = fallback

    async def chat(self, messages, tools=None) -> LLMResponse:
        try:
            return await self.primary.chat(messages, tools)
        except (RateLimitError, GroqUnavailableError):
            logger.warning("Primary LLM unavailable, falling back to secondary")
            return await self.fallback.chat(messages, tools)


class NoLLMAvailableError(Exception):
    pass


_llm_instance: LLMAdapter | None = None


def get_llm() -> LLMAdapter:
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance

    groq_key = config.GROQ_API_KEY
    gemini_key = config.GEMINI_API_KEY

    groq = GroqAdapter() if groq_key else None
    gemini = GeminiAdapter() if gemini_key else None

    if groq and gemini:
        _llm_instance = FailoverAdapter(groq, gemini)
    elif groq:
        _llm_instance = groq
    elif gemini:
        _llm_instance = gemini
    else:
        raise NoLLMAvailableError(
            "GROQ_API_KEY 또는 GEMINI_API_KEY를 설정해주세요."
        )

    return _llm_instance
