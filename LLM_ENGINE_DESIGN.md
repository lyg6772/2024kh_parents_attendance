# LLM Function Workflow Engine — 설계 문서

> **목적**: 자연어 지시를 실행 가능한 비즈니스 로직으로 변환하는 LLM 기반 워크플로우 엔진 PoC.
> 이 프로젝트(보람교사 출석 관리)는 PoC 대상 도메인이며, 엔진 자체는 다른 도메인에도 적용 가능하도록 설계한다.
> 기존 SSR 화면은 건드리지 않고 `app/agent/` 레이어를 추가하는 방식.

---

## 1. 핵심 설계 원칙

| 원칙 | 내용 |
|---|---|
| **엔진은 순수 실행기** | 비즈니스 규칙을 엔진 코드에 하드코딩하지 않는다 |
| **규칙은 시스템 프롬프트** | 워크플로우 순서, 제약사항은 자연어로 LLM에게 선언 |
| **안전 장치는 결정론적** | WRITE 오퍼레이션의 Confirmation 트리거는 코드가 보장. LLM 판단에 의존하지 않음 |
| **Tool 정의는 Type-Safe** | Pydantic 모델 기반. 오타/누락이 런타임이 아닌 정의 시점에 즉시 감지 |
| **히스토리는 클라이언트 보관** | 서버 Stateless. 클라이언트가 최근 15개 관리 |
| **기존 레이어 변경 최소화** | DAO 변경 없음. Service에 데이터 전용 메서드만 추가 |

---

## 2. 전체 아키텍처

```
클라이언트 (브라우저)
  │
  │  POST /agent/chat
  │  { "message": "4월 출석 알려줘", "history": [...최근 15개] }
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│  app/agent/router.py                                     │
│  - 인증 체크 (기존 get_current_user 재사용)              │
│  - engine.run() 호출                                     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  app/agent/engine.py  (LLM Function Workflow Engine)     │
│                                                          │
│  Stage 1  Intent Classifier                              │
│    REGISTRY summaries → LLM → fn_name[]                  │
│                                                          │
│  Stage 2  Slot Extractor + Data Mapper                   │
│    args_schema (JSON Schema) + context → LLM → kwargs   │
│    Pydantic validation → ArgumentError or pass           │
│                                                          │
│  Stage 3  Confirmation Gate  [결정론적]                  │
│    category == WRITE → 무조건 pending 반환               │
│    pending 메시지는 LLM이 자연어로 생성                  │
│                                                          │
│  Stage 4  Executor                                       │
│    REGISTRY[fn_name].handler(**validated_kwargs) → result│
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  app/agent/tools.py                                      │
│  ToolDefinition + Pydantic Args + REGISTRY               │
│  → 기존 Service 메서드 호출                              │
└────────────────────────┬────────────────────────────────┘
                         │
              기존 Service → DAO → Oracle DB
```

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
    READ  = "read"   # 순차 실행 자유, Confirmation 없음
    WRITE = "write"  # 한 턴 최대 1개, 항상 Confirmation


class ToolArgs(BaseModel):
    """모든 Tool Args 모델의 기반 클래스"""
    pass


@dataclass
class ToolDefinition:
    name:        str
    summary:     str               # Stage 1용 — 짧은 한 줄. LLM 함수 선택 기준
    description: str               # Stage 2용 — 맥락 + 사용 시점 설명
    category:    FunctionCategory
    args_schema: Type[ToolArgs]    # Pydantic 모델 → .model_json_schema() 자동 생성
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
    return await attendee_service.get_attendance_data(yyyymm)

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
    return await admin_service.post_attendance_data(date, attendee, notice)

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
    return await admin_service.export_attendance_data(yyyymm)

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

### ToolDefinition이 자동으로 제공하는 것

```python
# Stage 1 summaries 자동 생성
summaries = [
    {"name": t.name, "summary": t.summary}
    for t in REGISTRY.values()
]

# Stage 2 JSON Schema 자동 생성 (LLM 프롬프트용)
schema = REGISTRY["save_attendance"].args_schema.model_json_schema()
# → {"properties": {"date": {...}, "attendee": {...}, "notice": {...}}, ...}

# 인자 Validation
validated = SaveAttendanceArgs(**kwargs)  # 실패 시 ValidationError → ArgumentError

# Confirmation 트리거 (결정론적)
is_write = REGISTRY[fn_name].category == FunctionCategory.WRITE
```

---

## 4. 엔진 상세 설계

### Stage 1 — Intent Classifier

**입력**: 사용자 메시지 + 히스토리 + REGISTRY summaries (name + summary만)

**LLM 출력**

```python
class Stage1Result(BaseModel):
    fn_names: list[str]  # 순서 중요. 예: ["get_attendance", "save_attendance"]
    is_supported: bool   # 등록된 함수로 처리 가능한가
```

**제약**
- WRITE 함수는 목록에 최대 1개
- `is_supported=False` → 즉시 에러 메시지 반환

---

### Stage 2 — Slot Extractor + Data Mapper

**입력**: 사용자 메시지 + 선택된 함수의 `description` + `args_schema.model_json_schema()` + context (오늘 날짜)

**LLM 출력**: Structured Output — `args_schema` 모델 직접 사용

```python
# args_schema를 response_format으로 넘기면 LLM이 바로 채워줌
result: ToolArgs = await llm.complete(
    messages=[...],
    response_format=tool_def.args_schema,  # Pydantic 모델
)
validated_kwargs = result.model_dump()
```

**에러 처리**
- Pydantic validation 실패 → `ArgumentError` → 에러 메시지 즉시 반환 (추가 질문 없음)
- 예: "참석자 이름을 포함해서 다시 말씀해 주세요."

---

### Stage 3 — Confirmation Gate [결정론적]

**원칙**: WRITE category 감지는 코드가 보장. LLM 판단에 의존하지 않음.

```python
async def confirmation_gate(
    fn_name: str,
    kwargs: dict,
    llm: LLMAdapter,
    history: list[dict],
) -> ConfirmationResult:

    tool = REGISTRY[fn_name]

    # 트리거: 결정론적
    if tool.category != FunctionCategory.WRITE:
        return ConfirmationResult(required=False)

    # pending 메시지: LLM이 자연어로 생성
    message = await llm.complete(
        messages=history + [{
            "role": "system",
            "content": f"{fn_name}({kwargs})를 실행하려 합니다. "
                       f"사용자에게 한국어로 간결하게 확인 메시지를 작성하세요."
        }]
    )

    return ConfirmationResult(required=True, message=message, fn_name=fn_name, kwargs=kwargs)
```

---

### Stage 4 — Executor

```python
async def execute(fn_name: str, kwargs: dict) -> dict:
    tool = REGISTRY[fn_name]
    validated = tool.args_schema(**kwargs)      # 최종 validation
    return await tool.handler(**validated.model_dump())
```

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

**Response — 실행 완료 (READ)**
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

## 6. llm.py — LLM 어댑터

LLM 교체가 engine.py 수정 없이 가능하도록 어댑터 패턴 사용.

```python
class LLMAdapter(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        response_format: Type[BaseModel] | None = None,
    ) -> str | BaseModel: ...

class OpenAIAdapter(LLMAdapter):
    # response_format 있으면 client.chat.completions.parse() 사용 (Structured Output)
    # 없으면 client.chat.completions.create()

class AnthropicAdapter(LLMAdapter):
    # tool_use 방식으로 동일 인터페이스 구현

def get_llm() -> LLMAdapter:
    provider = config.LLM_PROVIDER  # "openai" | "anthropic"
    return OpenAIAdapter() if provider == "openai" else AnthropicAdapter()
```

**추가 환경변수 (app/.env)**
```
LLM_PROVIDER=openai
LLM_API_KEY=
LLM_MODEL=gpt-4o-2024-08-06
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
"""
```

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
    engine.py    Stage 1~4 실행 루프
    tools.py     ToolDefinition + Pydantic Args + REGISTRY
    llm.py       LLM 어댑터 (OpenAI / Anthropic)
    prompts.py   SYSTEM_PROMPT 등 프롬프트 상수
  service/
    attendee.py  get_attendance_data() 추가 (기존 메서드 유지)
    admin.py     post_attendance_data(), export_attendance_data() 추가
  # 나머지는 변경 없음
```

> parser.py 불필요 — Pydantic `.model_json_schema()`가 스키마 생성을 대체.

---

## 10. 기존 코드 재사용 범위

| 파일 | 처리 | 내용 |
|---|---|---|
| `dao/*.py` | ✅ 그대로 | 변경 없음 |
| `util/auth.py` | ✅ 그대로 | get_current_user 재사용 |
| `util/db.py` | ✅ 그대로 | DB Singleton 재사용 |
| `config.py` | ✅ + 확장 | LLM 환경변수 3개 추가 |
| `service/attendee.py` | ✅ + 추가 | 데이터 전용 메서드 신규 추가 |
| `service/admin.py` | ✅ + 추가 | 데이터 전용 메서드 신규 추가 |
| `controller/*.py` | ✅ 그대로 | 기존 SSR 핸들러 변경 없음 |

---

## 11. 구현 순서

```
1단계  service 메서드 추가
       AttendeeService.get_attendance_data(yyyymm: str) → dict
       AdminAttendeeService.post_attendance_data(date, attendee, notice) → dict
       AdminAttendeeService.export_attendance_data(yyyymm: str) → dict

2단계  app/agent/ 뼈대 생성
       tools.py  — ToolDefinition + Args 모델 + REGISTRY
       llm.py    — LLMAdapter + OpenAIAdapter
       prompts.py

3단계  engine.py 구현
       Stage 1 (Stage1Result Structured Output)
       Stage 2 (args_schema Structured Output)
       Stage 3 (결정론적 WRITE 감지)
       Stage 4 (handler 실행)

4단계  router.py 등록
       POST /agent/chat
       POST /agent/confirm
       main.py에 include_router

5단계  환경변수 추가
       LLM_PROVIDER, LLM_API_KEY, LLM_MODEL
```

각 단계마다 단위 테스트 작성 후 진행 (DEVELOPMENT.md TDD 원칙).

---

## 12. 미결 사항

| 항목 | 내용 |
|---|---|
| Stage 1/2 재시도 | LLM 파싱 실패 시 재시도 횟수 (1회 권장, 미확정) |
| export_excel URL | 파일 임시 저장 위치 및 URL 반환 방식 미정 |
| 에러 메시지 문구 | 한국어 에러 메시지 표준 정의 필요 |
| 멀티 READ 함수 순차 실행 | Stage 1이 fn_names[] 여러 개 반환 시 루프 처리 방식 |
