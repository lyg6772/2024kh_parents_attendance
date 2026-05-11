# LLM Function Workflow Engine — 설계 문서

> **목적**: 자연어 지시를 실행 가능한 비즈니스 로직으로 변환하는 LLM 기반 워크플로우 엔진 PoC.
> 이 프로젝트(보람교사 출석 관리)는 PoC 대상 도메인이며, 엔진 자체는 다른 도메인에도 적용 가능하도록 설계한다.
> 기존 SSR 화면은 건드리지 않고 `app/agent/` 레이어를 추가하는 방식.

---

## 1. 핵심 설계 원칙

| 원칙 | 내용 |
|---|---|
| **LLM이 판단, 코드가 실행** | 도구 선택과 조합은 LLM이 매 턴 자율 판단. 실행과 안전 장치는 코드가 담당 |
| **규칙은 시스템 프롬프트** | 워크플로우 순서, 제약사항은 자연어로 LLM에게 선언. 엔진 코드에 하드코딩하지 않음 |
| **안전 장치는 결정론적** | WRITE 오퍼레이션의 Confirmation 트리거는 코드가 보장. LLM 판단에 의존하지 않음 |
| **가드레일로 루프 제어** | MAX_TURNS, 도구 실패 시 중단 등 안전 장치를 코드로 강제 |
| **Tool 정의는 Type-Safe** | Pydantic 모델 기반. 오타/누락이 런타임이 아닌 정의 시점에 즉시 감지 |
| **히스토리는 클라이언트 보관** | 서버 Stateless. 클라이언트가 최근 15개 관리 |
| **기존 레이어 변경 최소화** | DAO 변경 없음. Service에 데이터 전용 메서드만 추가 |
| **모델 교체 가능** | LLMAdapter 추상화. Groq/Gemini failover 내장 |

---

## 2. 전체 아키텍처

```
클라이언트 (브라우저)
  │
  │  POST /agent/chat
  │  { "message": "4월 출석 알려줘", "history": [...최근 15개] }
  │
  ▼
┌──────────────────────────────────────────────────────────┐
│  app/agent/router.py                                      │
│  - 인증 체크 (기존 get_current_user 재사용)               │
│  - engine.run() 호출                                      │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  app/agent/engine.py  (ReAct Loop)                        │
│                                                           │
│  ┌─ Observe → Think → Act ─────────────────────────────┐ │
│  │                                                      │ │
│  │  1. LLM에게 현재 대화 + 도구 목록 전달               │ │
│  │  2. LLM 판단: 도구 호출 or 최종 응답                 │ │
│  │  3-a. 도구 호출 요청                                 │ │
│  │       → WRITE면 Confirmation Gate (결정론적)         │ │
│  │       → READ면 즉시 실행                             │ │
│  │       → 실행 결과를 대화에 추가                      │ │
│  │       → 1로 돌아감 (LLM이 결과 보고 다음 판단)       │ │
│  │  3-b. 최종 응답                                      │ │
│  │       → 사용자에게 반환                              │ │
│  │                                                      │ │
│  │  가드레일: MAX_TURNS 초과 시 강제 종료               │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│  app/agent/tools.py                                       │
│  ToolDefinition + Pydantic Args + REGISTRY                │
│  → 기존 데이터 서비스 호출                                │
└────────────────────────┬─────────────────────────────────┘
                         │
              기존 데이터 서비스 → DAO 함수 → Oracle DB
```

### 고정 파이프라인과의 차이

| | 이전 설계 (Stage 1→4) | 현재 설계 (ReAct) |
|---|---|---|
| 도구 선택 | Stage 1에서 한 번에 전부 결정 | 매 턴 LLM이 판단 |
| 인자 추출 | Stage 2에서 별도 LLM 호출 | function calling으로 도구 선택과 동시에 |
| 결과 반영 | 불가 — 도구 간 체이닝 없음 | 도구 A 결과를 보고 도구 B 인자 결정 가능 |
| LLM 호출 수 | 2-3회 고정 | 2-3회 (단순) ~ 5회 (복잡) |
| 중간 판단 | 없음 | 매 턴 "다음에 뭘 할지" 판단 |

---

## 3. ToolDefinition — Type-Safe Tool 정의

### 기반 타입

```python
# app/agent/tools.py

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Awaitable, Any, Type
from pydantic import BaseModel, Field


class FunctionCategory(str, Enum):
    READ  = "read"   # Confirmation 없이 즉시 실행
    WRITE = "write"  # 항상 Confirmation 필요 (코드가 강제)


class ToolArgs(BaseModel):
    """모든 Tool Args 모델의 기반 클래스"""
    pass


@dataclass
class ToolDefinition:
    name:        str
    summary:     str               # LLM function calling의 description에 포함
    description: str               # 시스템 프롬프트에 상세 용도 설명으로 포함
    category:    FunctionCategory
    args_schema: Type[ToolArgs]    # Pydantic 모델 → .model_json_schema() → function parameters
    handler:     Callable[..., Awaitable[dict]]  # 실제 실행 함수
```

### Tool 정의 예시

```python
# ─── get_attendance ───────────────────────────────────────

class GetAttendanceArgs(ToolArgs):
    yyyymm: str = Field(
        description="조회할 월. YYYYMM 형식.",
        examples=["202604"]
    )

async def _get_attendance(yyyymm: str) -> dict:
    return await attendance_service.get_attendance_data(yyyymm)

get_attendance_tool = ToolDefinition(
    name        = "get_attendance",
    summary     = "특정 월의 출석 현황 조회",
    description = (
        "날짜별 참석자 명단과 특이사항을 반환한다. "
        "출석 현황 확인 또는 저장/수정 전 기존 데이터 파악 용도로 사용한다."
    ),
    category    = FunctionCategory.READ,
    args_schema = GetAttendanceArgs,
    handler     = _get_attendance,
)


# ─── save_attendance ──────────────────────────────────────

class SaveAttendanceArgs(ToolArgs):
    date: str = Field(
        description="날짜. YYYYMMDD 형식.",
        examples=["20260403"]
    )
    attendee: str = Field(
        description="참석자. 쉼표 구분 문자열.",
        examples=["김철수,이영희"]
    )
    notice: str = Field(
        default="",
        description="특이사항. 없으면 빈 문자열."
    )

async def _save_attendance(date: str, attendee: str, notice: str = "") -> dict:
    return await attendance_service.save_attendance(date, attendee, notice)

save_attendance_tool = ToolDefinition(
    name        = "save_attendance",
    summary     = "특정 날짜 참석자/특이사항 저장 (기존 데이터 덮어쓰기)",
    description = (
        "지정한 날짜의 참석자 명단과 특이사항을 저장한다. "
        "기존 데이터가 있으면 완전히 덮어쓴다. "
        "반드시 저장 전에 get_attendance로 현황을 확인해야 한다."
    ),
    category    = FunctionCategory.WRITE,
    args_schema = SaveAttendanceArgs,
    handler     = _save_attendance,
)


# ─── export_excel ─────────────────────────────────────────

class ExportExcelArgs(ToolArgs):
    yyyymm: str = Field(
        description="대상 월. YYYYMM 형식.",
        examples=["202604"]
    )

async def _export_excel(yyyymm: str) -> dict:
    return await attendance_service.export_attendance_data(yyyymm)

export_excel_tool = ToolDefinition(
    name        = "export_excel",
    summary     = "특정 월 출석 현황 Excel 파일 생성 및 다운로드 URL 반환",
    description = "지정한 월의 출석 데이터를 Excel 파일로 생성하고 다운로드 URL을 반환한다.",
    category    = FunctionCategory.READ,
    args_schema = ExportExcelArgs,
    handler     = _export_excel,
)


# ─── Registry ─────────────────────────────────────────────

REGISTRY: dict[str, ToolDefinition] = {
    t.name: t for t in [
        get_attendance_tool,
        save_attendance_tool,
        export_excel_tool,
    ]
}
```

### REGISTRY → OpenAI function calling 스키마 자동 변환

```python
def registry_to_tools_param(registry: dict[str, ToolDefinition]) -> list[dict]:
    """REGISTRY를 LLM function calling의 tools 파라미터로 변환."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": f"{tool.summary}\n{tool.description}",
                "parameters": tool.args_schema.model_json_schema(),
            },
        }
        for tool in registry.values()
    ]

# Pydantic validation (도구 실행 전)
validated = SaveAttendanceArgs(**kwargs)  # 실패 시 ValidationError

# Confirmation 트리거 (결정론적)
is_write = REGISTRY[fn_name].category == FunctionCategory.WRITE
```

---

## 4. 엔진 상세 설계 — ReAct 루프

### 핵심 루프

LLM이 매 턴 "다음에 뭘 할지" 판단한다. 도구를 언제, 어떤 순서로, 몇 번 호출할지 LLM이 결정.
엔진은 실행과 안전 장치만 담당.

```python
# app/agent/engine.py

MAX_TURNS = 5  # 가드레일: 무한 루프 방지

async def run(
    message: str,
    history: list[dict],
    registry: dict[str, ToolDefinition],
    llm: LLMAdapter,
    session: AsyncSession,
) -> EngineResult:
    """
    ReAct 루프. LLM이 도구 호출 여부를 매 턴 판단.
    WRITE 도구는 코드가 Confirmation Gate를 강제.
    """
    tools_param = registry_to_tools_param(registry)
    messages = build_messages(message, history)

    for turn in range(MAX_TURNS):
        response = await llm.chat(messages, tools=tools_param)

        # ── LLM이 최종 응답을 선택한 경우 ──
        if response.is_final:
            return EngineResult(status="done", message=response.content)

        # ── LLM이 도구 호출을 요청한 경우 ──
        tool_call = response.tool_call
        tool = registry.get(tool_call.name)

        if tool is None:
            # 존재하지 않는 도구 호출 → 에러를 대화에 추가, 루프 계속
            messages.append(tool_error_message(tool_call.id, f"Unknown tool: {tool_call.name}"))
            continue

        # 인자 검증 (Pydantic)
        try:
            validated = tool.args_schema(**tool_call.arguments)
        except ValidationError as e:
            messages.append(tool_error_message(tool_call.id, str(e)))
            continue

        # ── Confirmation Gate (결정론적) ──
        if tool.category == FunctionCategory.WRITE:
            return EngineResult(
                status="pending_confirmation",
                message=response.content,  # LLM이 이미 확인 문구를 생성한 상태
                pending={"fn_name": tool_call.name, "kwargs": validated.model_dump()},
            )

        # ── READ 도구: 즉시 실행 ──
        result = await tool.handler(**validated.model_dump())

        # 실행 결과를 대화에 추가 → 다음 턴에서 LLM이 결과를 보고 판단
        messages.append(assistant_tool_call_message(tool_call))
        messages.append(tool_result_message(tool_call.id, result))

    # MAX_TURNS 초과
    return EngineResult(status="error", message="처리 한도를 초과했습니다. 요청을 더 간단하게 해주세요.")
```

### 메시지 빌더

```python
def build_messages(message: str, history: list[dict]) -> list[dict]:
    """시스템 프롬프트 + 히스토리 + 현재 메시지를 LLM 입력으로 조립."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(today=date.today().isoformat())},
        *history,
        {"role": "user", "content": message},
    ]

def tool_result_message(tool_call_id: str, result: dict) -> dict:
    """도구 실행 결과를 LLM 대화에 추가하는 메시지."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }

def tool_error_message(tool_call_id: str, error: str) -> dict:
    """도구 실행 실패를 LLM에게 알리는 메시지."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps({"error": error}, ensure_ascii=False),
    }
```

### Confirmation 확인 처리

```python
async def confirm(
    fn_name: str,
    kwargs: dict,
    approved: bool,
    registry: dict[str, ToolDefinition],
    session: AsyncSession,
) -> EngineResult:
    """사용자가 pending_confirmation에 응답한 후 호출."""
    if not approved:
        return EngineResult(status="done", message="취소했습니다.")

    tool = registry[fn_name]
    validated = tool.args_schema(**kwargs)
    result = await tool.handler(**validated.model_dump())
    return EngineResult(status="done", message=f"저장했습니다.")
```

### 가드레일 정리

| 가드레일 | 방식 | 담당 |
|---|---|---|
| WRITE Confirmation | `tool.category == WRITE` → 무조건 pending | 코드 (결정론적) |
| 무한 루프 방지 | `MAX_TURNS = 5` 초과 시 강제 종료 | 코드 (결정론적) |
| 잘못된 도구 호출 | REGISTRY에 없는 이름 → 에러 메시지 → 루프 계속 | 코드 (결정론적) |
| 인자 검증 실패 | Pydantic ValidationError → 에러 메시지 → 루프 계속 | 코드 (결정론적) |
| 도구 실행 실패 | handler 예외 → 에러 메시지 → 루프 계속 | 코드 (결정론적) |
| 워크플로우 순서 | "저장 전 조회" 등 → 시스템 프롬프트에 선언 | LLM (확률적) |

**원칙: 안전은 코드가, 판단은 LLM이.**

---

## 5. API 엔드포인트

### POST /agent/chat

**Request**
```json
{
  "message": "4월 3일 출석자 김철수, 이영희로 바꿔줘",
  "history": [
    {"role": "user",      "content": "4월 출석 현황 알려줘"},
    {"role": "assistant", "content": "4월 출석 현황입니다. ..."}
  ]
}
```

**Response — 실행 완료 (READ 또는 멀티턴 완료)**
```json
{
  "status": "done",
  "message": "4월 출석 현황입니다. 1일: 김철수, 이영희 / ..."
}
```

**Response — 확인 필요 (WRITE)**
```json
{
  "status": "pending_confirmation",
  "message": "4월 3일에 기존 출석자(박영수)가 있습니다. 김철수, 이영희로 덮어쓸까요?",
  "pending": {
    "fn_name": "save_attendance",
    "kwargs": {"date": "20260403", "attendee": "김철수,이영희", "notice": ""}
  }
}
```

**Response — 에러**
```json
{
  "status": "error",
  "message": "참석자 이름을 포함해서 다시 말씀해 주세요."
}
```

---

### POST /agent/confirm

**Request**
```json
{
  "approved": true,
  "pending": {
    "fn_name": "save_attendance",
    "kwargs": {"date": "20260403", "attendee": "김철수,이영희", "notice": ""}
  }
}
```

**Response**
```json
{
  "status": "done",
  "message": "저장했습니다."
}
```

---

## 6. llm.py — LLM 어댑터 (Groq + Gemini Failover)

### 모델 선정 근거

| | Groq (Llama 3.3 70B) | Gemini Flash |
|---|---|---|
| 역할 | **Primary** | Fallback |
| 속도 | 50-100ms | 1-3초 |
| 무료 한도 | 1,000 RPD | 250 RPD |
| Function calling | 네이티브, OpenAI 호환 | 네이티브, 자체 SDK |
| API 호환성 | OpenAI SDK 그대로 사용 | google-genai SDK |

### 어댑터 설계

```python
# app/agent/llm.py

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """LLM 응답의 통일된 표현."""
    is_final: bool            # True면 최종 응답, False면 도구 호출
    content: str | None       # 최종 응답 텍스트 (is_final=True일 때)
    tool_call: ToolCall | None  # 도구 호출 정보 (is_final=False일 때)


@dataclass
class ToolCall:
    id: str          # 도구 호출 ID (tool_call_id로 결과 매핑)
    name: str        # 도구 이름
    arguments: dict  # 파싱된 인자


class LLMAdapter(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse: ...


class GroqAdapter(LLMAdapter):
    """Groq API — OpenAI 호환 인터페이스. Primary."""
    def __init__(self):
        from groq import AsyncGroq
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY)
        self.model = config.GROQ_MODEL  # "llama-3.3-70b-versatile"

    async def chat(self, messages, tools=None) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else None,
        )
        choice = response.choices[0]

        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            return LLMResponse(
                is_final=False,
                content=choice.message.content,
                tool_call=ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ),
            )
        return LLMResponse(is_final=True, content=choice.message.content, tool_call=None)


class GeminiAdapter(LLMAdapter):
    """Google Gemini API. Fallback."""
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(config.GEMINI_MODEL)

    async def chat(self, messages, tools=None) -> LLMResponse:
        # Gemini SDK는 function calling 형식이 다름 — 변환 필요
        # 구현 시 OpenAI format → Gemini format 변환 레이어 작성
        ...


class FailoverAdapter(LLMAdapter):
    """Primary 실패 시 Fallback으로 자동 전환."""
    def __init__(self, primary: LLMAdapter, fallback: LLMAdapter):
        self.primary = primary
        self.fallback = fallback

    async def chat(self, messages, tools=None) -> LLMResponse:
        try:
            return await self.primary.chat(messages, tools)
        except RateLimitError:
            return await self.fallback.chat(messages, tools)


def get_llm() -> LLMAdapter:
    """환경 변수 기반 LLM 인스턴스 생성."""
    primary = GroqAdapter()
    fallback = GeminiAdapter()
    return FailoverAdapter(primary, fallback)
```

### 환경변수 (app/.env)

```
# Primary: Groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

# Fallback: Gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```

---

## 7. 시스템 프롬프트

비즈니스 규칙은 시스템 프롬프트에 선언. 엔진 코드에 하드코딩하지 않는다.

```python
SYSTEM_PROMPT = """
당신은 보람교사(급식 도우미) 출석 관리 어시스턴트입니다.
오늘 날짜: {today}

## 규칙
- "이번 달", "다음 달" 등 상대 날짜는 오늘 날짜 기준으로 YYYYMM / YYYYMMDD로 변환
- 저장/수정 요청이 들어오면 먼저 get_attendance로 기존 데이터를 조회하여 사용자에게 현황을 알릴 것
- 처리 결과는 간결한 한국어로 요약하여 응답
- 도구 호출 결과를 그대로 보여주지 말고, 사용자가 이해하기 쉽게 가공할 것
- 지원하지 않는 요청에는 "이 기능은 지원하지 않습니다"라고 안내
"""
```

**참고**: "저장 전 조회" 규칙은 시스템 프롬프트에 선언되어 있지만, LLM이 이를 무시할 수 있음.
이 경우에도 WRITE Confirmation Gate가 코드로 동작하므로, 사용자가 확인 없이 데이터가 변경되지는 않음.

---

## 8. 히스토리 관리 (클라이언트 책임)

서버는 히스토리를 저장하지 않는다. 클라이언트가 관리.

```typescript
interface Message {
  role:    "user" | "assistant"
  content: string
  status?: "done" | "active"
}

// 서버 요청 시
const history = messages
  .slice(-15)                        // 최근 15개 슬라이딩 윈도우
  .filter(m => m.status !== "done")  // 완료된 컨텍스트 제거 (선택)
```

---

## 9. 파일 구조

```
app/
  agent/
    __init__.py
    router.py    POST /agent/chat, POST /agent/confirm
    engine.py    ReAct 루프 + 가드레일
    tools.py     ToolDefinition + Pydantic Args + REGISTRY
    llm.py       LLMAdapter (Groq primary + Gemini fallback)
    prompts.py   SYSTEM_PROMPT 등 프롬프트 상수
  service/
    attendance.py       데이터 서비스 — get_attendance_data(), save_attendance() (신규)
    attendance_logic.py 순수 함수 — 날짜 파싱, 캘린더 생성 (신규)
    attendee.py         뷰 서비스 — 기존 SSR 유지
    admin.py            뷰 서비스 — 기존 SSR 유지
  # 나머지는 변경 없음
```

---

## 10. 기존 코드 재사용 범위

| 파일 | 처리 | 내용 |
|---|---|---|
| `dao/*.py` | ✅ 그대로 | 변경 없음 |
| `util/auth.py` | ✅ 그대로 | get_current_user 재사용 |
| `util/db.py` | ✅ + 확장 | get_session 함수 추가 |
| `config.py` | ✅ + 확장 | LLM 환경변수 추가 (Groq, Gemini) |
| `service/attendee.py` | ✅ + 위임 | 데이터 서비스에 위임, 렌더링만 담당 |
| `service/admin.py` | ✅ + 위임 | 데이터 서비스에 위임, 렌더링만 담당 |
| `controller/*.py` | ✅ 그대로 | 기존 SSR 핸들러 변경 없음 |

---

## 11. 구현 순서

```
1단계  데이터 서비스 + DAO 정비
       공통 DAO 함수 추출 (attendance.py)
       순수 함수 추출 (attendance_logic.py)
       데이터 서비스 구현 (attendance.py)

2단계  app/agent/ 뼈대 생성
       tools.py  — ToolDefinition + Args 모델 + REGISTRY
       llm.py    — LLMAdapter + GroqAdapter + GeminiAdapter + FailoverAdapter
       prompts.py

3단계  engine.py 구현
       ReAct 루프
       가드레일 (MAX_TURNS, Confirmation Gate, Validation)
       메시지 빌더

4단계  router.py 등록
       POST /agent/chat
       POST /agent/confirm
       main.py에 include_router

5단계  환경변수 추가
       GROQ_API_KEY, GROQ_MODEL
       GEMINI_API_KEY, GEMINI_MODEL
```

각 단계마다 단위 테스트 작성 후 진행 (DEVELOPMENT.md TDD 원칙).

---

## 12. 미결 사항

| 항목 | 내용 |
|---|---|
| MAX_TURNS 값 | 5를 기본으로 설정. 실 사용 후 조정 |
| export_excel URL | 파일 임시 저장 위치 및 URL 반환 방식 미정 |
| 에러 메시지 문구 | 한국어 에러 메시지 표준 정의 필요 |
| Gemini SDK 변환 레이어 | OpenAI tool calling format ↔ Gemini format 변환 구현 필요 |
| RPD 모니터링 | Groq/Gemini 일일 한도 추적 방식 (수동 카운터 vs 429 감지) |
| Confirmation 메시지 생성 | WRITE 감지 시 확인 메시지를 LLM이 자연어로 생성하는 방식 vs 정적 템플릿 |
