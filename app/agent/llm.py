import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app import config

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    is_final: bool
    content: str | None
    tool_call: ToolCall | None


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
            tc = msg.tool_calls[0]
            args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
            return LLMResponse(
                is_final=False,
                content=msg.content,
                tool_call=ToolCall(id=tc.id, name=tc.function.name, arguments=args),
            )

        return LLMResponse(is_final=True, content=msg.content, tool_call=None)


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

        part = resp.candidates[0].content.parts[0]  # type: ignore[index]

        if part.function_call:
            fc = part.function_call
            return LLMResponse(
                is_final=False,
                content=None,
                tool_call=ToolCall(
                    id=f"gemini_{fc.name}",
                    name=fc.name or "",
                    arguments=dict(fc.args) if fc.args else {},
                ),
            )

        return LLMResponse(is_final=True, content=part.text, tool_call=None)


def _openai_messages_to_gemini(messages: list[dict]) -> list[dict]:
    contents = []
    system_parts = []

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
            if msg.get("tool_calls"):
                tc = msg["tool_calls"][0]
                fn = tc["function"]
                args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                contents.append({
                    "role": "model",
                    "parts": [{"function_call": {"name": fn["name"], "args": args}}],
                })
            else:
                contents.append({"role": "model", "parts": [{"text": content or ""}]})
        elif role == "tool":
            tool_content = msg.get("content", "{}")
            result = json.loads(tool_content) if isinstance(tool_content, str) else tool_content
            contents.append({
                "role": "user",
                "parts": [{"function_response": {"name": "tool", "response": result}}],
            })

    return contents


def _strip_unsupported_keys(schema: dict) -> dict:
    """Gemini function declaration에서 지원하지 않는 키를 재귀적으로 제거한다."""
    unsupported = {"examples", "default", "$defs", "title"}
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


def get_llm() -> LLMAdapter:
    groq_key = config.GROQ_API_KEY
    gemini_key = config.GEMINI_API_KEY

    groq = GroqAdapter() if groq_key else None
    gemini = GeminiAdapter() if gemini_key else None

    if groq and gemini:
        return FailoverAdapter(groq, gemini)
    if groq:
        return groq
    if gemini:
        return gemini
    raise NoLLMAvailableError(
        "GROQ_API_KEY 또는 GEMINI_API_KEY를 설정해주세요."
    )
