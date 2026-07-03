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


class GroqAdapter(LLMAdapter):
    def __init__(self, api_key: str = "", model: str = ""):
        from groq import AsyncGroq

        self._client = AsyncGroq(api_key=api_key or config.GROQ_API_KEY)
        self._model = model or config.GROQ_MODEL

    async def chat(self, messages, tools=None) -> LLMResponse:
        from groq import RateLimitError as GroqRateLimit

        kwargs: dict = {"model": self._model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except GroqRateLimit as e:
            raise RateLimitError(str(e)) from e

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
        except RateLimitError:
            logger.warning("Primary LLM rate limited, falling back to secondary")
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
