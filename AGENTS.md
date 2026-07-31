# AGENTS.md — 2024kh_parents_attendance

학부모 보람교사(급식 도우미) 출석 관리 웹앱.  
FastAPI SSR (Jinja2) + LLM 챗봇 에이전트 (Groq/Gemini failover).

---

## Stack

- **Python 3.12+**, FastAPI, Uvicorn, async SQLAlchemy
- **DB**: Oracle (oracledb async driver), 로컬: SQLite (aiosqlite)
- **Template**: Jinja2 SSR
- **Auth**: JWT (HS256) → httpOnly cookie, bcrypt 패스워드
- **LLM**: Groq (primary) + Gemini (fallback), function calling 기반
- **Dependency manager**: Poetry

---

## Dev Commands

```bash
# 개발 서버
python run_app.py

# 또는 직접
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 테스트
poetry run pytest tests/ -v

# Docker
docker build -t kh-attendance .
docker run -p 8000:8000 --env-file app/.env kh-attendance
```

---

## Environment Setup

`.env` 파일은 **반드시 `app/.env`** 에 위치해야 함 (프로젝트 루트 아님).  
`config.py`가 `f'{os.getcwd()}/app/.env'`로 하드코딩됨 — 루트에 두면 무시됨.

필요한 환경 변수 목록은 `app/.env_example` 참조.

**주의**: `SECRET_SALT`가 비어있으면 앱 시작 시 `RuntimeError` 발생 (빈 키로 JWT 서명 방지).

---

## Architecture

```
app/
  main.py          # FastAPI 앱 팩토리, DB 초기화, 라우터 등록
  config.py        # dotenv 로드, 환경변수 노출, SECRET_SALT 검증
  controller/      # HTTP 핸들러 (router.py에서 수동 등록)
  service/         # 비즈니스 로직, Jinja2 렌더링
    attendance_data.py  # 에이전트용 출석 서비스 (JSON 반환)
    attendance_logic.py # 캘린더/날짜 순수 로직
  dao/             # SQLAlchemy ORM (select/delete + model)
  agent/           # LLM 챗봇 에이전트 레이어
    engine.py      # run() 루프 + confirm() — tool 실행 엔진
    tools.py       # ToolDefinition, Args schema, build_registry
    llm.py         # LLMAdapter (Groq/Gemini/Failover)
    prompts.py     # 시스템 프롬프트
    router.py      # /agent/chat, /agent/confirm 엔드포인트
  template/        # Jinja2 HTML 템플릿
  util/
    db.py          # DB Singleton — AsyncEngine + sessionmaker
    auth.py        # JWT encode/decode
    singleton.py   # SingletonMeta metaclass
```

**레이어 흐름**: `controller → service → DAO → DB`  
**에이전트 흐름**: `agent/router → engine → tools/service → DAO → DB`

레이어 경계 규칙은 `DEVELOPMENT.md` 참조.

---

## Critical Quirks

### Oracle 컬럼명 대소문자
SQLAlchemy `mappings().all()` 결과에서 Oracle은 컬럼명을 **대문자**로 반환.  
코드 전체에서 아래 패턴 사용 — 새 쿼리 추가 시 동일하게 적용:
```python
val = row.get('col_name') or row.get('COL_NAME')
```

### Jinja2 경로
- service에서 렌더링: `Jinja2Templates(directory="./app/template")` — 이것만 사용
- controller 파일에도 인스턴스가 존재하지만 실제 렌더링에는 사용하지 않음 (혼동 주의)

### DB Singleton
`DB` 클래스는 Singleton. `DB().init_db()`는 `main.py`의 `create_app()`에서 **한 번만** 호출.  
DAO에서는 `Depends(DB().get_db_session)`으로 세션 주입.

### INSERT 패턴
Oracle에 UPSERT 없이 **delete → insert** 패턴 사용:
```python
await session.execute(delete(Model).where(...))
session.add(Model(...))
await session.commit()
```

### 날짜 포맷
- URL param: `YYYYMM` (예: `202604`)
- DB 쿼리: `YYYYMMDD` 문자열 (예: `20260401`)
- 서비스 레이어에서 변환 처리

### LLM 에이전트 엔진
- `engine.run()`: LLM ↔ tool 루프 (MAX_TURNS=5). READ 도구는 즉시 실행, WRITE 도구는 confirmation gate.
- `engine.confirm()`: 사용자 승인/거부 처리. handler 예외 시 error 반환.
- `save_attendance` mode: `add`(기존+추가), `remove`(기존-제거), `set`(전체 교체). 기본값 `add`.
- preview: WRITE 도구에 `preview` 핸들러 등록 시, confirm 전 before→after 미리보기 제공.

---

## 개발 원칙

`DEVELOPMENT.md` 참조. 핵심 요약:

- AI는 **요청한 것만** 수정한다. 관련 없는 리팩토링 금지.
- 새 기능은 TDD — 테스트 먼저, 구현 나중.
- 레이어 경계를 지킨다 (controller → service → DAO).

---

## LLM 에이전트 구현 현황

- 기존 SSR 화면은 건드리지 않고 `app/agent/` 레이어를 **추가**한 방식
- 인증: 기존 쿠키 JWT 공유 (`/agent/*` 엔드포인트도 동일한 `get_current_user` 사용)
- LLM: Groq primary + Gemini fallback (`FailoverAdapter`)
- 도구 6개: `get_attendance`, `save_attendance`, `export_excel`, `navigate_month`, `logout`, `get_help`

---

## Harness (moru)

이 레포는 moru 하네스로 초기화되어 있다 (`.agents/`, `scripts/`, `tests/harness/`).
파이프라인 본문은 `.agents/workflow.md` 가 소유하고, 이 절은 그 진입점과 하드 규칙만
갖는다.

### 큰 그림 먼저

범위를 판단하거나 설계 결정을 내리기 **전에** `docs/OVERVIEW.md` 를 읽고, 거기서
갈라지는 문서를 따라간다. **대화만 보고 추론하지 않는다** — 가장 흔한 실패는 전체
그림을 못 본 채 조각으로 판단하는 것이다. 필요한 것이 문서에 없으면 코드에서 찾아
답한 뒤, 어느 문서가 그걸 담았어야 하는지 밝힌다.

### 파이프라인

| 진입점 | 쓰는 때 |
|---|---|
| `/dev "<작업>"` | 일반 작업 — 0→7 스테이지 전체 |
| `/feature-dev "<기능>"` | 큰 기능 — 분해 후 리프별 실행 |
| `/discover` | 코드베이스 규약 심화 (`.agents/context/codebase-conventions.md`) |

스테이지 정의는 `.agents/00-*.md` ~ `.agents/07-*.md`. 사람이 개입하는 지점은
설계 게이트 승인과 모호함 질의 응답 두 곳이다.

### Quick commands

```bash
poetry run pytest -q                     # 테스트 (tests/harness 는 기본 수집에서 빠진다)
poetry run ruff check .                  # 린트 — 기존 부채 있음, 훅에 비차단으로 물림
poetry run ruff format --check --diff .  # 포맷 — 검사만. 재작성하지 않는다
poetry run pyright app                   # 타입 — 기존 부채 있음
```

레포별 검증 축과 부채는 `.agents/context/codebase-conventions.md` 가 소유한다.
**부채 건수를 여기 옮겨 적지 않는다** — 규칙 선택과 검사 범위에 따라 움직이는
값이라 복제하면 조용히 낡는다. 숫자가 필요하면 위 명령을 돌린다.

### 하드 규칙

- **TDD + 테스트 잠금.** 테스트를 먼저 쓰고, `.agents/context/locks/` 에 잠긴
  테스트는 구현을 통과시키려고 고치지 않는다. 테스트가 오라클이다.
- **레이어 방향을 지킨다** — controller → service → dao. 역방향 import 금지.
- **비밀을 커밋하지 않는다.** `app/.env` 는 추적 대상이 아니고, 새 비밀은 환경변수로.
- **증상이 아니라 근본 원인을 고친다.** 예외를 삼키거나 검사를 끄는 것은 수정이 아니다.
- **기본 브랜치에 직접 푸시하지 않는다.** 브랜치 → PR. 머지는 사람이 한다.
- **새 의존성은 사람 승인이 필요하다.** 추가 이유와 대안을 먼저 제시한다.
- **도구·스킬 우선.** 실질 작업을 직접 하기 **전에** 그걸 커버하는 스킬/커맨드가
  있는지 확인하고 있으면 그걸로 실행한다 (비용 티어링과 엄밀성이 거기 설계돼 있다).
  다중 소스 조사는 `/research`, PR 은 `ship-pr` 스킬. 건너뛰면 사유를 먼저 밝힌다.

### 리뷰-수정 루프 상한

pre-push 게이트(`scripts/pr_review_gate.sh`)는 **수렴을 보장하지 않는다** — 라운드마다
새 지적이 나오므로 판정 없이 고치고 재푸시하면 끝나지 않는다.

1. **한 브랜치 3라운드 상한.** 3라운드 안에 PASS 못 하면 멈추고 미해결 지적 목록과
   함께 사람에게 보고한다. 4번째 푸시는 없다. "한 번만 더"가 떠오르는 순간이 보고
   시점이다. (게이트는 4번째 **연속** BLOCK 을 LLM 호출 전에 거부한다 — 그 거부는
   에이전트가 이 규칙을 이미 안다고 전제한다.)
2. **리뷰는 입력이고 판정은 내 것이다.** 심각도 라벨을 그대로 수용하지 않는다.
   지적마다 **내가** 판정한다: 안 고치면 뭐가 잘못되나(효과) → 고치면 뭐가
   깨지나(부작용) → 채택/기각/후속. **기각이 정상 결과다** — 사유를 PR 본문에 남기면
   그 지적은 처리된 것이다. 판정 없는 수정이 루프의 연료다.
3. **같은 계열(같은 파일·같은 주제) 지적이 2번째 오면 패치 금지.** 계열을 없애는
   설계로 바꾸거나 사람에게 넘긴다.
4. **루프 중 범위 확장 금지.** 이번 작업 밖 결함은 후속 과제로만 적는다.

### 협업 프로파일

`.agents/collaboration.md` 는 이 팀의 작업 방식 프로파일이다. 세션마다 읽고,
관측한 것을 덧붙인다 (선호하는 판단 축, 반복되는 지적, 하지 말라고 한 것).
