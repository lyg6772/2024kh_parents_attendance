import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.agent.llm import LLMAdapter, LLMResponse, ToolCall
from app.agent.prompts import build_system_prompt
from app.agent.tools import FunctionCategory, ToolDefinition, TOOLS_PARAM

MAX_TURNS = 5


@dataclass
class EngineResult:
    status: str
    message: str
    pending: dict[str, Any] | None = field(default=None)
    redirect: str | None = field(default=None)


def build_messages(
    message: str,
    history: list[dict],
) -> list[dict]:
    system = build_system_prompt(
        today=date.today().isoformat(),
    )
    return [
        {"role": "system", "content": system},
        *history,
        {"role": "user", "content": message},
    ]


def assistant_tool_call_message(tool_call: ToolCall) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.name,
                    "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
                },
            }
        ],
    }


def tool_result_message(tool_call_id: str, result: dict) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


def tool_error_message(tool_call_id: str, error: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps({"error": error}, ensure_ascii=False),
    }


async def run(
    message: str,
    history: list[dict],
    registry: dict[str, ToolDefinition],
    llm: LLMAdapter,
) -> EngineResult:
    tools_param = TOOLS_PARAM
    messages = build_messages(message, history)

    for turn in range(MAX_TURNS):
        response = await llm.chat(messages, tools=tools_param)

        if response.is_final:
            return EngineResult(status="done", message=response.content or "")

        tool_call = response.tool_call
        if tool_call is None:
            return EngineResult(status="done", message=response.content or "")

        tool = registry.get(tool_call.name)

        if tool is None:
            messages.append(tool_error_message(tool_call.id, f"Unknown tool: {tool_call.name}"))
            continue

        try:
            validated = tool.args_schema(**(tool_call.arguments or {}))
        except ValidationError as e:
            messages.append(tool_error_message(tool_call.id, str(e)))
            continue

        if tool.category == FunctionCategory.WRITE:
            preview = None
            if tool.preview:
                try:
                    preview = await tool.preview(**validated.model_dump())
                except Exception:
                    pass

            return EngineResult(
                status="pending_confirmation",
                message=response.content or "",
                pending={
                    "fn_name": tool_call.name,
                    "kwargs": validated.model_dump(),
                    "preview": preview,
                },
            )

        try:
            result = await tool.handler(**validated.model_dump())
        except Exception as e:
            messages.append(tool_error_message(tool_call.id, str(e)))
            continue

        if "redirect_url" in result:
            return EngineResult(
                status="done",
                message=result.get("message", ""),
                redirect=result["redirect_url"],
            )

        messages.append(assistant_tool_call_message(tool_call))
        messages.append(tool_result_message(tool_call.id, result))

    return EngineResult(status="error", message="처리 한도를 초과했습니다. 요청을 더 간단하게 해주세요.")


async def confirm(
    fn_name: str,
    kwargs: dict,
    approved: bool,
    registry: dict[str, ToolDefinition],
    message: str = "",
    history: list[dict] | None = None,
    llm: LLMAdapter | None = None,
) -> EngineResult:
    if not approved:
        return EngineResult(status="done", message="취소했습니다.")

    tool = registry[fn_name]
    validated = tool.args_schema(**kwargs)

    try:
        await tool.handler(**validated.model_dump())
    except Exception:
        return EngineResult(status="error", message="저장 실패: 잠시 후 다시 시도해주세요.")

    redirect = None
    kw = validated.model_dump()
    if "date" in kw:
        redirect = f"/admin/attendee/{kw['date'][:6]}"

    return EngineResult(status="done", message="저장했습니다.", redirect=redirect)
