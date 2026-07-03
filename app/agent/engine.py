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


def _append_tool_error(messages: list[dict], tool_call: ToolCall, error: str) -> None:
    # tool 메시지는 반드시 직전 assistant의 tool_calls를 참조해야 함 (OpenAI 호환 API 제약).
    # 누락 시 다음 llm.chat() 호출이 400으로 실패해 자가수정 루프 전체가 죽는다.
    messages.append(assistant_tool_call_message(tool_call))
    messages.append(tool_error_message(tool_call.id, error))


async def _build_pending(
    item: dict,
    remaining: list[dict],
    registry: dict[str, ToolDefinition],
    message: str = "",
) -> EngineResult:
    """확인 대기(pending_confirmation) 결과를 만든다. item의 preview를 계산하고
    아직 처리 못 한 나머지 계획(remaining)을 queue로 함께 실어 보낸다."""
    tool = registry[item["fn_name"]]
    preview = None
    if tool.preview:
        try:
            preview = await tool.preview(**item["kwargs"])
        except Exception:
            pass
    return EngineResult(
        status="pending_confirmation",
        message=message,
        pending={
            "fn_name": item["fn_name"],
            "kwargs": item["kwargs"],
            "preview": preview,
            "queue": remaining,
        },
    )


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

        if not response.tool_calls:
            return EngineResult(status="done", message=response.content or "")

        # 한 응답에 담긴 도구 호출을 순서대로 훑는다.
        #  - 첫 WRITE 이전의 READ: 즉시 실행 (결과는 다음 턴 종합용으로 messages에 축적)
        #  - 첫 WRITE부터 그 뒤의 모든 호출: 확인 게이트 뒤로 큐잉 → 승인 시 LLM 없이 소진
        queue: list[dict] = []
        gate_open = False
        batch_error = False

        for tool_call in response.tool_calls:
            tool = registry.get(tool_call.name)

            if tool is None:
                _append_tool_error(messages, tool_call, f"Unknown tool: {tool_call.name}")
                batch_error = True
                break

            try:
                validated = tool.args_schema(**(tool_call.arguments or {}))
            except ValidationError as e:
                _append_tool_error(messages, tool_call, str(e))
                batch_error = True
                break

            if gate_open or tool.category == FunctionCategory.WRITE:
                gate_open = True
                queue.append({"fn_name": tool_call.name, "kwargs": validated.model_dump()})
                continue

            try:
                result = await tool.handler(**validated.model_dump())
            except Exception as e:
                _append_tool_error(messages, tool_call, str(e))
                batch_error = True
                break

            if "redirect_url" in result:
                return EngineResult(
                    status="done",
                    message=result.get("message", ""),
                    redirect=result["redirect_url"],
                )

            messages.append(assistant_tool_call_message(tool_call))
            messages.append(tool_result_message(tool_call.id, result))

        if batch_error:
            continue  # 에러를 대화에 넣었으니 모델이 고쳐서 재시도하도록 다음 턴

        if queue:
            return await _build_pending(queue[0], queue[1:], registry, message=response.content or "")

        # 전부 READ였고 결과를 축적했으니 다음 턴에서 모델이 종합
    return EngineResult(status="error", message="처리 한도를 초과했습니다. 요청을 더 간단하게 해주세요.")


async def confirm(
    fn_name: str,
    kwargs: dict,
    approved: bool,
    registry: dict[str, ToolDefinition],
    queue: list[dict] | None = None,
) -> EngineResult:
    if not approved:
        return EngineResult(status="done", message="취소했습니다.")

    tool = registry[fn_name]
    validated = tool.args_schema(**kwargs)

    try:
        await tool.handler(**validated.model_dump())
    except Exception:
        return EngineResult(status="error", message="저장 실패: 잠시 후 다시 시도해주세요.")

    kw = validated.model_dump()
    redirect = f"/admin/attendee/{kw['date'][:6]}" if "date" in kw else None

    # 남은 계획을 LLM 재호출 없이 순서대로 소진한다. 다음 WRITE를 만나면 멈추고
    # 그 확인을 다시 요청(연속 저장), redirect READ를 만나면 그 redirect로 종료(저장+엑셀).
    # ponytail: 모델이 계획을 한 응답에 병렬로 안 주면 큐가 짧아 여기서 조용히 끝난다
    #   (남은 작업은 유저가 다시 요청). 완결성이 더 중요해지면 마지막에 run() 1회 재진입 추가.
    remaining = list(queue or [])
    for i, item in enumerate(remaining):
        item_tool = registry[item["fn_name"]]
        item_validated = item_tool.args_schema(**item["kwargs"])

        if item_tool.category == FunctionCategory.WRITE:
            return await _build_pending(item, remaining[i + 1:], registry)

        try:
            result = await item_tool.handler(**item_validated.model_dump())
        except Exception:
            return EngineResult(status="error", message="처리 실패: 잠시 후 다시 시도해주세요.")

        if "redirect_url" in result:
            return EngineResult(status="done", message="", redirect=result["redirect_url"])
        # redirect 없는 READ 결과는 소비할 LLM이 없어 폐기 (실사용상 write 뒤 READ는 redirect류)

    return EngineResult(status="done", message="저장했습니다.", redirect=redirect)
