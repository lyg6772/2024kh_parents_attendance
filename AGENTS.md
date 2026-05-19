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
