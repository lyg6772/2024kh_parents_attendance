# LLM Engine 구현 계획서

> 보람교사 출석 관리 앱에 LLM 에이전트 레이어를 추가하기 위한 구현 계획.
> `llm_engine_design.md`의 설계를 기반으로, 현재 코드베이스의 구조적 문제를 함께 해결한다.

---

## 0. 작업 규약

### 0.1 용어 정의

프로젝트 전체에서 아래 용어를 일관되게 사용한다.

| 용어 | 의미 | 예시 |
|---|---|---|
| **DAO 함수** | DB 세션을 받아 SQL을 실행하는 async 함수. IO만 담당 | `get_attendee(session, start_dt, end_dt)` |
| **순수 함수** | 외부 의존 없이 입력→출력만 하는 함수. 테스트 쉬움 | `build_calendar_context(year, month)`, `parse_date_range(yyyymm)` |
| **데이터 서비스** | DAO 함수 + 순수 함수를 조합해 **데이터(dict)만** 반환. 렌더링 없음. 에이전트/API용 | `get_attendance_data(session, yyyymm) → dict` |
| **뷰 서비스** | 데이터 서비스 결과를 받아 **HTML(TemplateResponse)**로 렌더링. SSR 전용 | 기존 `AttendeeService.get_attendee_table()` — 리팩토링 후 |
| **엔진** | LLM 에이전트의 ReAct 루프 전체. 도구 선택/조합을 LLM이 매 턴 자율 판단 | `engine.run()` |
| **ReAct 루프** | 엔진 내부의 반복 흐름 (Observe → Think → Act → 결과 관찰 → 반복 or 응답) | `while turn < MAX_TURNS` |
| **가드레일** | 코드로 강제하는 안전 장치. MAX_TURNS, WRITE Confirmation, Pydantic validation | 결정론적 — LLM 판단에 의존하지 않음 |
| **도구(Tool)** | 엔진이 호출하는 등록된 함수 단위. ToolDefinition으로 정의 | `get_attendance`, `save_attendance` |
| **레지스트리** | 도구 이름 → ToolDefinition 매핑 딕셔너리 | `REGISTRY: dict[str, ToolDefinition]` |

**"서비스"를 단독으로 쓰지 않는다** — 항상 "데이터 서비스" 또는 "뷰 서비스"로 구분.

### 0.2 작업 프로토콜

| 항목 | 규칙 |
|---|---|
| **작업 단위** | 기능/문제 단위. "DAO 중복 해결", "ReAct 루프 구현" 같은 단위로 진행 |
| **판단 위임** | 파일 구조 변경 등 큰 결정만 확인. 함수명, 변수명 등 세부는 알아서 진행 |
| **완료 기준** | 코드 + 테스트 통과. 커밋은 별도 요청 시에만 |
| **기존 코드** | 래퍼 패턴으로 기존 인터페이스 유지. SSR이 깨지면 안 됨 |

### 0.3 의사결정 히스토리

설계/방향성에 대한 결정 사항을 기록한다. 의견 충돌 시 근거로 사용.

#### DR-001: FP 전환 범위 (2025-05-11)

**질문**: 코드베이스를 Functional Programming으로 전환할 것인가?

**결정**: Practical FP. 풀 FP 아닌 실용적 수준.

**근거**:
- 현재 클래스들이 사실상 함수를 위장하고 있음 (self.dao가 유일한 상태, 다형성/상속 없음)
- Python은 FP 언어가 아님 — 모나드, effect system은 오버엔지니어링
- 클래스를 벗기면 코드가 더 명확해짐 (DAO 중복 해소, 테스트 용이)
- 상태가 필요한 곳(LLMAdapter)만 클래스. 나머지는 plain function

**기각한 대안**:
- 풀 FP: Python 생태계와 맞지 않음
- 현상 유지 (OOP): DAO 중복, 로직/렌더링 혼합 문제 해결 불가

---

#### DR-002: 엔진 아키텍처 — ReAct vs 고정 파이프라인 (2025-05-11)

**질문**: 엔진을 고정 Stage 1→4 파이프라인으로 할 것인가, ReAct 루프로 할 것인가?

**결정**: ReAct 루프 + 가드레일.

**근거**:
- 원래 의도가 "LLM이 기능들을 보고 유기적으로 조합/조율" — 이건 ReAct에 해당
- 고정 파이프라인은 Stage 1에서 모든 도구를 한 번에 결정 → 중간 결과 반영 불가
- 도구가 3개라 ReAct와 고정 파이프라인의 LLM 호출 횟수 차이 미미 (2-3회 vs 2-3회)
- function calling은 원래 도구 선택 + 인자 추출을 한 번에 하는데, 기존 설계가 이를 Stage 1/2로 인위적으로 분리했음
- 가드레일(MAX_TURNS, WRITE Confirmation, Pydantic validation)로 안전성 확보

**기각한 대안**:
- 고정 파이프라인: 유기적 조합 불가, 원래 의도와 불일치
- 하이브리드 (READ은 고정, WRITE만 ReAct): 구현 복잡도 대비 이점 불명확

---

#### DR-003: 모델 선정 — 무료 모델 + Failover (2025-05-11)

**질문**: 어떤 LLM 모델을 사용할 것인가?

**결정**: Groq (Llama 3.3 70B) Primary + Gemini Flash Fallback.

**근거**:
- 무료 모델 사용 전제 (비용 0원 목표)
- Groq: 가장 빠름 (50-100ms), function calling 안정적, OpenAI 호환, 1000 RPD 무료
- Gemini Flash: Groq RPD 소진 시 fallback용, 250 RPD 추가 확보
- 도구 3개에서 올바른 도구 선택은 Llama 70B로 충분 (GPT-4o 대비 ~80%, 하지만 난이도가 낮음)
- ReAct 루프의 약한 모델 리스크(무한 루프, 잘못된 도구 선택)는 가드레일로 대응

**기각한 대안**:
- GPT-4o: 유료, 이 도메인에서 성능 차이 체감 어려움
- Gemini 단독: RPD 250으로 부족, 속도도 Groq 대비 느림
- 로컬 모델 (Ollama): 서버 리소스 부담, 배포 복잡도 증가

---

#### DR-004: 용어 체계 — 역할 기반 네이밍 (2025-05-11)

**질문**: 코드베이스 용어를 어떻게 통일할 것인가?

**결정**: 역할 기반 네이밍. "서비스"를 단독으로 쓰지 않는다.

**근거**:
- "서비스"가 3가지 의미로 혼용됨 (HTML 반환, 데이터 반환, 비즈니스 로직 전반)
- "데이터 서비스" / "뷰 서비스"로 구분하면 대화 시 혼동 없음
- "엔진" / "ReAct 루프" / "가드레일" / "도구" / "레지스트리" — 에이전트 레이어 용어도 역할로 구분

**기각한 대안**:
- 기존 이름 그대로: "서비스"의 의미 모호함이 계속됨
- 자유 명명 (맥락으로 구분): 문서화 시 혼란, 새 참여자 진입 장벽

---

#### DR-005: 작업 프로토콜 (2025-05-11)

**질문**: 작업 단위, 판단 위임, 완료 기준을 어떻게 할 것인가?

**결정**:
- 작업 단위: 기능/문제 단위
- 판단 위임: 큰 것만 확인 (파일 구조 변경 등). 함수명/변수명은 알아서
- 완료 기준: 코드 + 테스트 통과. 커밋은 별도 요청

**근거**:
- Phase 단위는 방향 틀어지면 되돌리기 큼
- 파일 단위는 세밀하지만 느림
- 기능 단위가 중간 확인 가능 + 실용적 속도

---

#### DR-006: 테스트 전략 — Unit Test 우선 (2025-05-11)

**질문**: 어떤 레벨의 테스트를 먼저 작성할 것인가?

**결정**: Unit test 우선. E2E는 후순위.

**근거**:
- 순수 함수(날짜 계산, 캘린더 생성, 데이터 병합)는 DB/LLM 없이 100% 검증 가능
- 엔진 ReAct 루프도 LLM mock으로 단위 테스트 가능 (가드레일, Confirmation Gate 등)
- E2E는 Oracle DB + LLM API + HTTP 서버 전부 필요 — 시간 대비 효율 낮음
- Integration test (DAO)는 실제 Oracle 필요 — 로컬 개발 환경에서 제약

**기각한 대안**:
- E2E 우선: 환경 구축 비용 큼, 디버깅 어려움
- Integration 우선: 순수 함수/엔진 로직 검증이 더 시급

#### DR-007: Confirm 재진입 — continuation prompt 방식 (2025-05-12)

**질문**: WRITE 승인 후 후속 작업(예: 엑셀 출력)을 어떻게 이어갈 것인가?

**결정**: `confirm()` → `run()` 재진입 시 원래 메시지 대신 continuation prompt 사용.

**근거**:
- `build_messages()`가 `message`를 마지막 user 메시지로 붙이므로, 원래 메시지를 그대로 넘기면 LLM이 새 요청으로 인식 → 같은 WRITE를 반복 호출 → **무한루프**
- history에 이미 원래 요청이 포함되어 있으므로, 재진입 시에는 "나머지 작업을 진행해주세요"라는 continuation prompt만 전달
- LLM은 history에서 원래 요청과 완료된 작업을 파악하고, 미처리 작업만 이어서 실행

**기각한 대안**:
- 원래 메시지 그대로 전달: 무한루프 발생 확인
- `build_messages()`에서 중복 메시지 감지/제거: 복잡도 증가, 엣지케이스 많음

#### DR-008: Confirm 후 페이지 새로고침 정책 (2025-05-12)

**질문**: WRITE 승인 후 SSR 테이블을 어떻게 갱신할 것인가?

**결정**: confirm 응답의 모든 종료 경로(`done`, `redirect`)에서 auto-reload.

**근거**:
- `done` + `approved`: WRITE가 실행되었으므로 SSR 테이블이 stale → 2.5초 후 reload
- `redirect` (파일 다운로드): `Content-Disposition: attachment` 응답은 페이지를 떠나지 않으므로, 다운로드 시작 후 2.5초 뒤 reload하면 SSR 테이블도 갱신
- 페이지 이동 redirect (navigate_month 등): `window.location.href` 시점에 JS 컨텍스트 파괴 → reload 타이머 자동 취소, 부작용 없음

**기각한 대안**:
- 수동 새로고침 버튼: 유저에게 추가 동작 요구, UX 저하
- reload 안 함: SSR 테이블이 stale 상태로 남음

#### DR-009: LLM 어댑터 싱글턴 캐싱 (2025-05-12)

**질문**: `get_llm()`이 매 요청마다 `AsyncGroq()` + `genai.Client()`를 재생성하는 비효율을 어떻게 해결할 것인가?

**결정**: 모듈 레벨 `_llm_instance` 변수로 싱글턴 캐싱. 최초 호출 시 1회 생성, 이후 재사용.

**근거**:
- `AsyncGroq`/`genai.Client`는 내부에 `httpx.AsyncClient` 기반 connection pool을 생성 — 매번 새로 만들면 커넥션 재활용 불가, GC 부담
- API 키는 앱 실행 중 변경되지 않으므로 인스턴스 재사용 안전
- `chat()` 호출 시 `messages`/`tools`를 인자로 받으므로 요청 간 상태 격리 보장 (stateless 전송 계층)

**기각한 대안**:
- 매 요청 생성 유지: 커넥션 풀 재활용 불가, 요청 증가 시 성능 저하
- FastAPI `Depends` 캐싱: `get_llm`은 request scope가 아닌 app scope여야 하므로 부적합

#### DR-010: TOOLS_PARAM 모듈 상수 (2025-05-12)

**질문**: `registry_to_tools_param()`이 매 `run()` 호출마다 `model_json_schema()` x6을 재생성하는 비효율을 어떻게 해결할 것인가?

**결정**: `tools.py`에서 `TOOLS_PARAM = registry_to_tools_param(REGISTRY)`를 모듈 로드 시 1회 생성. `engine.run()`에서 상수 참조.

**근거**:
- `model_json_schema()`는 Pydantic 모델 리플렉션으로 JSON Schema dict 생성 — 결과가 불변
- `build_registry(session)`은 handler만 교체하고 name/description/schema는 동일 → `tools_param`은 REGISTRY 기준으로 충분
- 순수 dict/list 상수이므로 동시 읽기 안전 (Python GIL + 불변 데이터)

**기각한 대안**:
- `ToolDefinition`에 `_cached_schema` 프로퍼티: 각 인스턴스마다 캐시 관리 필요, 복잡도 증가
- `functools.lru_cache`: dict 입력이 hashable이 아니어서 직접 사용 불가

#### DR-011: 토큰 절약 — 시스템 프롬프트 도구 목록 제거 + description 압축 (2025-05-12)

**질문**: 매 LLM 호출마다 토큰 소비를 줄일 수 있는가?

**결정**: 3가지 동시 적용.
1. 시스템 프롬프트에서 `## 사용 가능한 도구` 섹션 제거
2. 각 tool의 description에서 "사용 시점" trigger 예시 삭제, 핵심 동작 지시만 유지
3. `registry_to_tools_param`에서 `f"{summary}\n{description}"` → `description`만 사용

**근거**:
- `tools` 파라미터가 LLM에 도구 정보를 전달하는 정식 채널. 시스템 프롬프트의 도구 목록은 100% 중복 → ~400토큰 낭비
- "사용 시점: '엑셀로 뽑아줘', '엑셀 다운로드'..." 같은 trigger 예시는 함수 이름 + 간결한 description만으로 충분히 매핑 가능
- `f"{summary}\n{description}"`에서 summary는 description의 요약이므로 중복

**영향**: 매 호출 ~500토큰 절약. `build_system_prompt()` 시그니처 단순화 (registry 파라미터 제거).

**기각한 대안**:
- 시스템 프롬프트에 도구 목록 유지 (안전성): 도구 6개로 소규모, 중복 제거해도 선택 정확도 저하 무시 가능
- description 유지하고 trigger만 제거: 부분 개선이지만, 이왕 정리하는 김에 전체 압축이 효과적

---

## 1. 현재 코드베이스 진단

### 1.1 구조 요약

```
controller (5 endpoints)  →  service (3 classes)  →  DAO (3 classes)  →  DB (Singleton)
```

| 레이어 | 파일 | 역할 |
|---|---|---|
| Controller | `login.py`, `attendee.py`, `admin.py` | Request 수신, Depends로 서비스 주입, 응답 반환 |
| Service | `login.py`, `attendee.py`, `admin.py` | 비즈니스 로직 + Jinja2 렌더링 혼합 |
| DAO | `login.py`, `attendee.py`, `admin.py` | Raw SQL (`text()`) 실행 |
| DB | `util/db.py` | Singleton AsyncEngine + sessionmaker |

### 1.2 발견된 문제점

**A. 클래스가 함수를 위장하고 있다**

모든 서비스/DAO 클래스가 동일한 패턴:

```python
class AttendeeService:
    def __init__(self, dao: AttendeeDao = Depends(AttendeeDao)):
        self.dao = dao

    async def get_attendee_table(self, request, date_str):
        # self.dao만 사용 — 인스턴스 상태 없음
```

- `self.dao`가 유일한 인스턴스 변수
- 다형성, 상속, 캡슐화 없음
- 클래스가 DI 컨테이너 역할만 하고 있음 — **불필요한 ceremony**

**B. DAO 코드 중복**

`AttendeeDao`와 `AdminAttendeeDao`에 **완전히 동일한 메서드**가 존재:

```python
# AttendeeDao.get_attendee()  — attendee.py
# AdminAttendeeDao.get_attendee()  — admin.py
# → 동일한 SQL, 동일한 파라미터, 동일한 반환값
```

`get_notice()`도 마찬가지. 클래스로 나눴기 때문에 공유가 안 되는 것.

**C. 비즈니스 로직과 렌더링이 혼합**

```python
async def get_attendee_table(self, request, date_str):
    # 1. 날짜 계산 (순수 로직)
    # 2. DAO 호출 (IO)
    # 3. 딕셔너리 조립 (순수 로직)
    # 4. TemplateResponse 반환 (렌더링)
```

하나의 메서드에 순수 로직 + IO + 렌더링이 섞여 있어서:
- LLM 에이전트가 데이터만 필요할 때 재사용 불가
- 단위 테스트 시 Request 객체와 Jinja2를 모킹해야 함

**D. 글로벌 상태 산재**

```python
# service/login.py
templates = Jinja2Templates(directory="./app/template")  # 모듈 레벨
pwd_context = CryptContext(schemes=["bcrypt"])            # 모듈 레벨
auth = AuthHandler()                                      # 모듈 레벨
```

각 서비스 파일마다 글로벌 인스턴스가 흩어져 있음.

---

## 2. FP 전환 여부 — "Practical FP"

### 2.1 풀 FP를 하지 않는 이유

- Python은 FP 언어가 아님 — 모나드, effect system은 오버엔지니어링
- FastAPI의 `Depends()`는 함수/클래스 둘 다 지원 — 굳이 패러다임을 강제할 필요 없음
- 기존 SSR은 동작 중 — 이념적 리팩토링으로 깨뜨릴 이유 없음

### 2.2 Practical FP를 해야 하는 이유

현재 코드의 "OOP"는 사실상 FP가 맞다:

| 현재 패턴 | 실제 의미 |
|---|---|
| `class AttendeeService` | 함수 2개를 묶은 네임스페이스 |
| `self.dao` | 함수 인자로 받아야 할 의존성 |
| `class AttendeeDao` | async 함수 + session 인자 |
| `DB() Singleton` | 모듈 레벨 팩토리 함수 |

**클래스를 벗기면 코드가 더 명확해진다:**

```python
# Before (현재)
class AttendeeDao:
    def __init__(self, db_session=Depends(DB().get_db_session)):
        self.session = db_session
    async def get_attendee(self, start_dt, end_dt):
        async with self.session as session:
            result = await session.execute(query, params)
            return result.mappings().all()

# After (Practical FP)
async def get_attendee(session: AsyncSession, start_dt: str, end_dt: str) -> list[dict]:
    result = await session.execute(query, params)
    return result.mappings().all()
```

### 2.3 적용 원칙

| 원칙 | 설명 |
|---|---|
| **순수 함수 우선** | IO가 없는 로직(날짜 계산, 딕셔너리 조립, 캘린더 생성)은 순수 함수로 추출 |
| **effects at boundaries** | IO(DB, LLM API)는 함수 경계에서만 발생. 내부 로직은 순수하게 유지 |
| **클래스는 필요할 때만** | 상태가 필요한 경우(LLMAdapter 등)만 클래스. 나머지는 plain function |
| **Depends()는 유지** | FastAPI DI는 함수에도 동작 — 클래스 없이도 주입 가능 |

---

## 3. 리팩토링 계획

### Phase 0: 기반 정비

**목표**: 새 코드가 의존할 기반을 정리. 기존 동작 변경 없음.

#### 0-1. Config 확장

```python
# app/config.py — 추가
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
```

#### 0-2. DB 세션 의존성을 독립 함수로 분리

현재 `DB().get_db_session`은 Singleton 메서드. 이걸 모듈 레벨 함수로 노출:

```python
# app/util/db.py — 추가
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends()용 세션 팩토리. DB Singleton 내부 구현을 감춤."""
    async with DB()._async_session_maker() as session:
        yield session
```

기존 DAO의 `Depends(DB().get_db_session)`은 당장 안 바꿈 — 새 코드만 `get_session` 사용.

#### 0-3. 테스트 인프라 구축

```toml
# pyproject.toml — dev dependencies 추가
[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
httpx = "^0.27"
```

```
tests/
  conftest.py          # DB 세션 fixture, test client
  test_dao/
  test_service/
  test_agent/
```

---

### Phase 1: DAO 리팩토링

**목표**: DAO 클래스를 plain async function으로 전환. 코드 중복 제거.

#### 1-1. 공통 DAO 함수 추출

```python
# app/dao/attendance.py (신규 — 기존 attendee.py, admin.py의 중복 통합)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_attendee(session: AsyncSession, start_dt: str, end_dt: str) -> list[dict]:
    """출석자 목록 조회. AttendeeDao와 AdminAttendeeDao에서 동일했던 쿼리."""
    query = text("""...""")
    result = await session.execute(query, {"start_dt": start_dt, "end_dt": end_dt})
    return [dict(row) for row in result.mappings().all()]


async def get_notice(session: AsyncSession, start_dt: str, end_dt: str) -> list[dict]:
    """특이사항 조회."""
    query = text("""...""")
    result = await session.execute(query, {"start_dt": start_dt, "end_dt": end_dt})
    return [dict(row) for row in result.mappings().all()]


async def upsert_attendee(session: AsyncSession, date: str, attendee_list: list[str]) -> None:
    """출석자 저장 (delete → insert)."""
    await session.execute(delete_query, {"date": date})
    for name in attendee_list:
        await session.execute(insert_query, {"date": date, "name": name})
    await session.commit()


async def upsert_notice(session: AsyncSession, date: str, notice: str) -> None:
    """특이사항 저장 (delete → insert)."""
    await session.execute(delete_query, {"date": date})
    await session.execute(insert_query, {"date": date, "notice": notice})
    await session.commit()
```

#### 1-2. 기존 DAO 클래스 — 래퍼로 유지

기존 서비스가 `Depends(AttendeeDao)` 패턴을 쓰고 있으므로, 기존 DAO 클래스는 새 함수를 위임 호출하는 래퍼로 남긴다. SSR 엔드포인트가 깨지지 않도록.

```python
# app/dao/attendee.py — 기존 파일 수정
from app.dao.attendance import get_attendee as _get_attendee, get_notice as _get_notice

class AttendeeDao:
    def __init__(self, db_session=Depends(DB().get_db_session)):
        self.session = db_session

    async def get_attendee(self, start_dt, end_dt):
        async with self.session as session:
            return await _get_attendee(session, start_dt, end_dt)
```

새 agent 코드는 DAO 함수를 직접 호출. 기존 SSR 코드는 래퍼 클래스를 계속 사용.

**테스트**: 기존 SSR 엔드포인트가 동일하게 동작하는지 통합 테스트.

---

### Phase 2: Service 레이어 분리

**목표**: 비즈니스 로직(순수)과 렌더링(IO)을 분리. LLM 에이전트가 데이터만 가져갈 수 있도록.

#### 2-1. 순수 함수 추출

```python
# app/service/attendance_logic.py (신규)

import calendar
from datetime import datetime


def build_calendar_context(year: int, month: int) -> dict:
    """달력 렌더링에 필요한 컨텍스트 생성. 순수 함수."""
    cal = calendar.Calendar(firstweekday=6)
    weeks = cal.monthdayscalendar(year, month)
    return {
        "year": year,
        "month": month,
        "weeks": weeks,
        "prev_month": ...,
        "next_month": ...,
    }


def parse_date_range(date_str: str) -> tuple[str, str, int, int]:
    """YYYYMM → (start_dt, end_dt, year, month). 순수 함수."""
    year = int(date_str[:4])
    month = int(date_str[4:6])
    start_dt = f"{date_str}01"
    last_day = calendar.monthrange(year, month)[1]
    end_dt = f"{date_str}{last_day}"
    return start_dt, end_dt, year, month
```

#### 2-2. 데이터 전용 서비스 함수 (에이전트용)

```python
# app/service/attendance.py (신규 — 에이전트 + API용)

from sqlalchemy.ext.asyncio import AsyncSession
from app.dao import attendance as dao
from app.service.attendance_logic import parse_date_range, build_calendar_context


async def get_attendance_data(session: AsyncSession, yyyymm: str) -> dict:
    """데이터만 반환. HTML 렌더링 없음. 에이전트/API 공용."""
    start_dt, end_dt, year, month = parse_date_range(yyyymm)
    attendees_raw = await dao.get_attendee(session, start_dt, end_dt)
    notices_raw = await dao.get_notice(session, start_dt, end_dt)
    cal_ctx = build_calendar_context(year, month)

    # Oracle 컬럼명 정규화 (inline)
    attendees = {
        (r.get("atdc_date") or r.get("ATDC_DATE")): (r.get("atde_name") or r.get("ATDE_NAME") or "")
        for r in attendees_raw if (r.get("atdc_date") or r.get("ATDC_DATE"))
    }
    notices = {
        (r.get("atdc_date") or r.get("ATDC_DATE")): (r.get("atdc_notice") or r.get("ATDC_NOTICE") or "")
        for r in notices_raw if (r.get("atdc_date") or r.get("ATDC_DATE"))
    }

    return {**cal_ctx, "attendees": attendees, "notices": notices}


async def save_attendance(session: AsyncSession, date: str, attendee: str, notice: str = "") -> dict:
    """출석 저장. 에이전트용."""
    attendee_list = [name.strip() for name in attendee.split(",") if name.strip()]
    await dao.upsert_attendee(session, date, attendee_list)
    if notice:
        await dao.upsert_notice(session, date, notice)
    return {"saved": True, "date": date, "count": len(attendee_list)}
```

#### 2-3. 기존 SSR 서비스 — 새 함수에 위임

```python
# app/service/attendee.py — 기존 파일 수정

class AttendeeService:
    def __init__(self, dao: AttendeeDao = Depends(AttendeeDao)):
        self.dao = dao

    async def get_attendee_table(self, request, date_str):
        # 기존: 모든 로직이 여기 있었음
        # 수정: 순수 함수 + 데이터 서비스에 위임, 렌더링만 담당
        data = await get_attendance_data(session, date_str or default_date())
        return templates.TemplateResponse("attendee.html", {**data, "request": request})
```

**테스트**: 순수 함수 단위 테스트 + SSR 통합 테스트.

---

### Phase 3: Agent 레이어 구현

**목표**: `llm_engine_design.md` 설계 그대로 구현. ReAct 루프 + 가드레일.

#### 3-1. 파일 구조

```
app/agent/
  __init__.py
  tools.py       # ToolDefinition + Args + REGISTRY
  engine.py      # ReAct 루프 + 가드레일
  llm.py         # LLMAdapter (Groq primary + Gemini fallback)
  prompts.py     # 시스템 프롬프트 상수
  router.py      # POST /agent/chat, POST /agent/confirm
```

#### 3-2. Engine — ReAct 루프

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
    ReAct 루프. LLM이 도구 호출 여부를 매 턴 자율 판단.
    WRITE 도구는 코드가 Confirmation Gate를 강제.
    """
    tools_param = registry_to_tools_param(registry)
    messages = build_messages(message, history)

    for turn in range(MAX_TURNS):
        response = await llm.chat(messages, tools=tools_param)

        # LLM이 최종 응답을 선택
        if response.is_final:
            return EngineResult(status="done", message=response.content)

        # LLM이 도구 호출을 요청
        tool_call = response.tool_call
        tool = registry.get(tool_call.name)

        if tool is None:
            messages.append(tool_error_message(tool_call.id, f"Unknown tool: {tool_call.name}"))
            continue

        # 인자 검증 (Pydantic)
        try:
            validated = tool.args_schema(**tool_call.arguments)
        except ValidationError as e:
            messages.append(tool_error_message(tool_call.id, str(e)))
            continue

        # Confirmation Gate (결정론적)
        if tool.category == FunctionCategory.WRITE:
            return EngineResult(
                status="pending_confirmation",
                message=response.content,
                pending={"fn_name": tool_call.name, "kwargs": validated.model_dump()},
            )

        # READ 도구: 즉시 실행, 결과를 대화에 추가
        result = await tool.handler(**validated.model_dump())
        messages.append(assistant_tool_call_message(tool_call))
        messages.append(tool_result_message(tool_call.id, result))

    return EngineResult(status="error", message="처리 한도를 초과했습니다.")
```

#### 3-3. 가드레일 — 코드가 보장하는 안전 장치

| 가드레일 | 방식 | 담당 |
|---|---|---|
| WRITE Confirmation | `tool.category == WRITE` → 무조건 pending | 코드 |
| 무한 루프 방지 | `MAX_TURNS = 5` 초과 시 강제 종료 | 코드 |
| 잘못된 도구 호출 | REGISTRY에 없는 이름 → 에러 → 루프 계속 | 코드 |
| 인자 검증 | Pydantic ValidationError → 에러 → 루프 계속 | 코드 |
| 워크플로우 순서 | "저장 전 조회" 등 → 시스템 프롬프트 | LLM |

#### 3-4. LLMAdapter — Groq Primary + Gemini Fallback

```python
# app/agent/llm.py

class LLMAdapter(ABC):
    @abstractmethod
    async def chat(self, messages, tools=None) -> LLMResponse: ...

class GroqAdapter(LLMAdapter):
    """Groq (Llama 3.3 70B) — Primary. OpenAI 호환 인터페이스."""
    def __init__(self):
        from groq import AsyncGroq
        self.client = AsyncGroq(api_key=config.GROQ_API_KEY)
        self.model = config.GROQ_MODEL

class GeminiAdapter(LLMAdapter):
    """Google Gemini Flash — Fallback."""
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(config.GEMINI_MODEL)

class FailoverAdapter(LLMAdapter):
    """Primary 429(Rate Limit) 시 Fallback으로 자동 전환."""
    def __init__(self, primary: LLMAdapter, fallback: LLMAdapter):
        self.primary = primary
        self.fallback = fallback

    async def chat(self, messages, tools=None) -> LLMResponse:
        try:
            return await self.primary.chat(messages, tools)
        except RateLimitError:
            return await self.fallback.chat(messages, tools)

def get_llm() -> LLMAdapter:
    return FailoverAdapter(GroqAdapter(), GeminiAdapter())
```

#### 3-5. Router

```python
# app/agent/router.py

agent_router = APIRouter(prefix="/agent", tags=["agent"])

@agent_router.post("/chat")
async def chat(
    body: ChatRequest,
    user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    llm = get_llm()
    result = await engine.run(body.message, body.history, REGISTRY, llm, session)
    return result.to_response()

@agent_router.post("/confirm")
async def confirm(
    body: ConfirmRequest,
    user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    ...
```

---

### Phase 4: 통합 및 검증

#### 4-1. main.py에 agent router 등록

```python
from app.agent.router import agent_router
app.include_router(agent_router)
```

#### 4-2. 인증 확장 (선택)

기존 쿠키 JWT + API Key 병행. `llm_engine_design.md` DEVELOPMENT.md 5절 참조.

#### 4-3. 환경 변수 추가

```
# app/.env
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
GEMINI_API_KEY=AI...
GEMINI_MODEL=gemini-2.0-flash
```

`app/.env_example`에도 빈 값으로 추가.

---

## 4. 구현 순서 및 의존 관계

```
Phase 0  기반 정비
  ├─ 0-1 Config 확장
  ├─ 0-2 DB 세션 함수 분리
  └─ 0-3 테스트 인프라 구축
         │
Phase 1  DAO 리팩토링
  ├─ 1-1 공통 DAO 함수 추출 (attendance.py)
  └─ 1-2 기존 DAO 클래스 래퍼화
         │
Phase 2  Service 분리
  ├─ 2-1 순수 함수 추출 (attendance_logic.py)
  ├─ 2-2 데이터 전용 서비스 (attendance.py)
  └─ 2-3 기존 SSR 서비스 위임 전환
         │
Phase 3  Agent 레이어 구현
  ├─ 3-1 tools.py (ToolDefinition + REGISTRY)
  ├─ 3-2 engine.py (ReAct 루프 + 가드레일)
  ├─ 3-3 llm.py (GroqAdapter + GeminiAdapter + FailoverAdapter)
  ├─ 3-4 prompts.py
  └─ 3-5 router.py
         │
Phase 4  통합 및 검증
  ├─ 4-1 main.py 등록
  ├─ 4-2 인증 확장 (선택)
  └─ 4-3 환경 변수
```

각 Phase 완료 후 테스트 통과 확인. Phase 간 독립 배포 가능.

---

## 5. 파일 변경 요약

| 파일 | 변경 유형 | Phase |
|---|---|---|
| `app/config.py` | 확장 (Groq/Gemini 환경변수 4개) | 0 |
| `app/util/db.py` | 확장 (get_session 함수 추가) | 0 |
| `pyproject.toml` | 확장 (dev deps, groq, google-genai) | 0, 3 |
| `app/.env_example` | 확장 (Groq/Gemini 환경변수) | 0 |
| `app/dao/attendance.py` | **신규** — 공통 DAO 함수 | 1 |
| `app/dao/attendee.py` | 수정 — 래퍼로 전환 | 1 |
| `app/dao/admin.py` | 수정 — 래퍼로 전환 | 1 |
| `app/service/attendance_logic.py` | **신규** — 순수 함수 | 2 |
| `app/service/attendance.py` | **신규** — 데이터 전용 서비스 | 2 |
| `app/service/attendee.py` | 수정 — 위임 전환 | 2 |
| `app/service/admin.py` | 수정 — 위임 전환 | 2 |
| `app/agent/__init__.py` | **신규** | 3 |
| `app/agent/tools.py` | **신규** | 3 |
| `app/agent/engine.py` | **신규** — ReAct 루프 + 가드레일 | 3 |
| `app/agent/llm.py` | **신규** — Groq/Gemini/Failover 어댑터 | 3 |
| `app/agent/prompts.py` | **신규** | 3 |
| `app/agent/router.py` | **신규** | 3 |
| `app/main.py` | 수정 (router 등록 1줄) | 4 |

기존 `controller/` 파일은 **변경 없음**. SSR 동작 보장.

---

## 6. 리스크 및 미결 사항

| 항목 | 리스크 | 대응 |
|---|---|---|
| Phase 1-2에서 기존 SSR 깨질 가능성 | 중간 | 래퍼 패턴으로 기존 인터페이스 유지. 통합 테스트 필수 |
| Oracle 컬럼명 대소문자 | 낮음 | 기존 이중 `.get()` 패턴 그대로 유지 |
| LLM 무한 루프 | 중간 | MAX_TURNS=5 가드레일로 강제 종료 |
| LLM이 WRITE를 조회 없이 실행 | 낮음 | Confirmation Gate가 코드로 차단. 시스템 프롬프트에도 규칙 선언 |
| Groq RPD 한도 초과 | 중간 | Gemini fallback 자동 전환. 일일 사용량은 수십 건 수준 예상 |
| Gemini SDK 변환 복잡도 | 중간 | OpenAI format ↔ Gemini format 변환 레이어 필요 |
| 기존 DAO 세션 관리 방식과 새 `get_session` 혼용 | 낮음 | 새 코드만 `get_session` 사용. 점진적 마이그레이션 |

---

## 7. Practical FP 적용 기준 요약

```
사용하는 것                              사용하지 않는 것
──────────────────────────────────────  ──────────────────────────────────────
순수 함수 (날짜, 캘린더, 데이터 변환)      모나드, Effect system
함수 합성 (engine ReAct loop)            커링, 부분 적용 남발
불변 데이터 (dict, dataclass)             모든 곳에 frozen=True 강제
명시적 의존성 주입 (함수 인자)             암묵적 글로벌 상태
클래스는 상태가 있을 때만 (LLMAdapter)     모든 것을 클래스로 감싸기
```

---

## 8. 테스트 전략 및 요구사항

### 8.1 테스트 레벨

| 레벨 | 범위 | 이 프로젝트에서 | 비고 |
|---|---|---|---|
| **Unit Test** | 함수/모듈 단위 | ✅ 핵심 — Phase 2, 3 전체 | DB/LLM mock으로 격리 |
| Integration Test | DB/API 연동 | ⏸ 후순위 — Phase 1 (DAO) | 실제 Oracle 필요 |
| E2E Test | 전체 흐름 | ⏸ 후순위 | DB + LLM + HTTP 전부 필요, 시간 대비 효율 낮음 |

Unit test만으로 순수 함수 + 엔진 ReAct 루프 + 가드레일 + Pydantic validation + Failover를 전부 검증 가능.

### 8.2 요구사항: Phase 2 — 순수 함수 (attendance_logic.py)

DB/LLM 없이 100% unit test 가능.

| ID | 요구사항 | 입력 예시 | 기대 출력 |
|---|---|---|---|
| **P2-01** | `parse_date_range`는 YYYYMM을 start_dt, end_dt, year, month로 변환 | `"202604"` | `("20260401", "20260430", 2026, 4)` |
| **P2-02** | `parse_date_range`는 월말 날짜를 정확히 계산 (28/29/30/31) | `"202602"` | end_dt=`"20260228"` (윤년이면 29) |
| **P2-03** | `build_calendar_context`는 해당 월의 주별 날짜 배열 반환 | `(2026, 4)` | weeks 배열, 일요일 시작 (firstweekday=6) |
| **P2-04** | `build_calendar_context`는 이전/다음 월 정보 포함 | `(2026, 12)` | next_month = `"202701"` (연도 넘김) |

> P2-05~07 (`merge_attendance_data`) 삭제됨. 출석자/특이사항은 별도 JSON key로 반환하므로 병합 불필요. 정규화는 데이터 서비스에서 inline 처리.

### 8.3 요구사항: Phase 3-A — ToolDefinition + REGISTRY

| ID | 요구사항 | 테스트 방법 |
|---|---|---|
| **P3-01** | `args_schema.model_json_schema()`가 유효한 JSON Schema 반환 | 각 Tool의 스키마에 필수 필드 존재 확인 |
| **P3-02** | 유효한 인자로 Pydantic 모델 생성 성공 | `GetAttendanceArgs(yyyymm="202604")` → 정상 |
| **P3-03** | 잘못된 인자로 ValidationError 발생 | `SaveAttendanceArgs()` (필수 필드 누락) → 에러 |
| **P3-04** | REGISTRY에 모든 도구 등록 확인 | `len(REGISTRY) == 3`, 이름 일치 |
| **P3-05** | `registry_to_tools_param`이 OpenAI function calling 형식 반환 | 각 항목에 type, function.name, function.parameters 존재 |
| **P3-06** | READ/WRITE 카테고리 정확히 분류 | get_attendance=READ, save_attendance=WRITE, export_excel=READ |

### 8.4 요구사항: Phase 3-B — 엔진 ReAct 루프 (LLM mock)

| ID | 요구사항 | 시나리오 | 기대 결과 |
|---|---|---|---|
| **P3-10** | 단순 READ 요청 처리 | LLM → get_attendance 호출 → 결과 요약 | `status="done"` |
| **P3-11** | WRITE 요청 시 Confirmation Gate 작동 | LLM → save_attendance 호출 | `status="pending_confirmation"`, pending에 fn_name+kwargs |
| **P3-12** | Confirmation 승인 시 실행 | `confirm(approved=True)` | 도구 handler 호출됨, `status="done"` |
| **P3-13** | Confirmation 거부 시 취소 | `confirm(approved=False)` | handler 호출 안 됨, `status="done"`, "취소" |
| **P3-14** | MAX_TURNS 초과 시 강제 종료 | LLM이 계속 도구 호출 (5회 초과) | `status="error"` |
| **P3-15** | 존재하지 않는 도구 호출 시 에러 후 루프 계속 | LLM → "unknown_tool" 호출 | 에러 메시지가 대화에 추가, 루프 다음 턴 진행 |
| **P3-16** | 인자 검증 실패 시 에러 후 루프 계속 | LLM → save_attendance(date 누락) | ValidationError가 대화에 추가, 루프 다음 턴 |
| **P3-17** | 멀티스텝: 조회 후 저장 | LLM → get_attendance → 결과 확인 → save_attendance | 첫 도구 실행 후 결과가 messages에 추가, 두 번째 도구에서 Confirmation |
| **P3-18** | LLM이 도구 호출 없이 바로 응답 | 지원 불가 요청 | `status="done"`, 자연어 응답 |

### 8.5 요구사항: Phase 3-C — FailoverAdapter (LLM mock)

| ID | 요구사항 | 시나리오 | 기대 결과 |
|---|---|---|---|
| **P3-20** | Primary 정상 시 Primary 사용 | Groq 정상 응답 | GroqAdapter.chat 호출됨 |
| **P3-21** | Primary RateLimit 시 Fallback 전환 | Groq 429 에러 | GeminiAdapter.chat 호출됨 |
| **P3-22** | Fallback도 실패 시 에러 전파 | 둘 다 실패 | 예외 발생 |

### 8.6 테스트 파일 구조

```
tests/
  conftest.py                 # 공통 fixture (LLM mock, REGISTRY mock 등)
  test_attendance_logic.py    # P2-01 ~ P2-04
  test_tools.py               # P3-01 ~ P3-06
  test_engine.py              # P3-10 ~ P3-18
  test_failover.py            # P3-20 ~ P3-22
```

---

## 9. 향후 개선 TODO

### TODO-001: 도구(Tool) 자동 등록 — 데코레이터 기반

**현재 문제**: 도구 1개 추가 시 3곳 수동 동기화 필요.
1. `tools.py` — `XxxArgs(ToolArgs)` Pydantic 모델 + `ToolDefinition` 인스턴스 + `REGISTRY` 딕셔너리
2. `tools.py build_registry()` — handler 매핑 추가
3. `attendance_data.py` — 서비스 함수 (필요 시)

**개선 방안**: 데코레이터로 함수 정의와 동시에 자동 등록.

```python
# Before (현재 — 3곳 수동 동기화)
class GetAttendanceArgs(ToolArgs):
    yyyymm: str = Field(description="조회할 월")

get_attendance_tool = ToolDefinition(
    name="get_attendance", summary="...", description="...",
    category=READ, args_schema=GetAttendanceArgs, handler=_stub,
)

REGISTRY = { "get_attendance": get_attendance_tool, ... }

# build_registry() 에도 handler 매핑 추가 필요

# After (목표 — 함수 하나면 끝)
@tool(name="get_attendance", category=READ, summary="특정 월의 출석 현황 조회")
async def get_attendance(session: AsyncSession, yyyymm: str = Field(..., description="조회할 월")) -> dict:
    dr = parse_date_range(yyyymm)
    ...
    return {"attendees": ...}
```

**구현 포인트**:
- `@tool` 데코레이터가 함수 시그니처에서 `ToolArgs` Pydantic 모델 자동 생성
- `session` 파라미터는 스키마에서 제외 (DI로 주입)
- 데코레이터 적용 시 글로벌 `REGISTRY`에 자동 등록
- `build_registry()`는 session closure만 주입하는 역할로 단순화

**전환 시점**: 도구가 10개 이상으로 늘어나거나, 도구 추가 빈도가 잦아질 때.
현재 5개 수준에서는 수동 관리가 더 명확하고 디버깅 쉬움.
