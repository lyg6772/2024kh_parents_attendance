# 코드베이스 규약 — 2024kh_parents_attendance

> 이 파일은 레포마다 재생성된다 (`.agents/PORTING.md`). 아래는 moru-init 시점
> (2026-07-31) 의 발굴 패스 결과이고, `/discover` 가 나중에 깊게 채운다.
> **구조의 진실은 실코드다** — 여기 적힌 것과 코드가 다르면 코드가 맞다.

## 스택

| | |
|---|---|
| 언어 | Python 3.12 |
| 패키지 매니저 | **poetry** (`package-mode = false` — 앱이지 라이브러리가 아니다) |
| 웹 | FastAPI + uvicorn, Jinja2 템플릿 |
| DB | SQLAlchemy 2.x async + aiomysql / pymysql, oracledb. 테스트는 aiosqlite |
| 인증 | PyJWT + passlib[bcrypt] |
| LLM | groq, google-genai |

## 레이아웃

```
app/
  main.py          FastAPI 앱 · @app.get · @app.exception_handler
  config.py        설정 (고위험)
  controller/      라우트 계층
  service/         비즈니스 로직 + models.py (계층 간 DTO)
  dao/             데이터 접근 + tables.py (ORM 정의 — 모든 DAO 가 읽는다)
  agent/           LLM 에이전트: engine · llm · prompts · router · tools
  util/            auth.py(JWT) · db.py(세션) · singleton.py  ← 공유면
  template/        Jinja2
tests/             pytest, conftest.py 가 aiosqlite 인메모리 세션 픽스처 제공
```

**계층 방향**: controller → service → dao. `service/models.py` 가 계층 간 DTO 를
소유하고, `dao/tables.py` 가 ORM 을 소유한다.

## 검증 커맨드

`06-verification.md` 가 이 절을 읽어 순서대로 실행한다.

| 축 | 커맨드 | 상태 |
|---|---|---|
| 린트 | `poetry run ruff check .` | **부채 있음** — init 시점 75건 (아래) |
| 포맷 | `poetry run ruff format .` | init 시점 22파일 미적용 |
| 타입 | `poetry run pyright app` | **부채 있음** — init 시점 25건 |
| 테스트 | `poetry run pytest -q` | `testpaths = ["tests"]`, `asyncio_mode = "auto"` |
| e2e | *(미정)* | 앱 실기동 경로가 아직 정의되지 않았다 |
| 커버리지 | *(없음)* | 커버리지 도구 미설치 → **stage-6 §2-2 는 N/A 로 하강한다** |

## 테스트 규약

- 파일명 `tests/test_*.py`, 클래스로 묶는다 (`class TestArgsSchema:`)
- 테스트마다 주석으로 케이스 ID 를 단다 (`# P3-01: ...`) — 설계 문서의 요구사항과
  잇는 관용구다. 신규 테스트도 이 형식을 따른다
- async 테스트는 `asyncio_mode = "auto"` 라 데코레이터가 필요 없다
- DB 가 필요한 테스트는 `db_session` 픽스처를 받는다 (aiosqlite 인메모리,
  테이블은 매 테스트 생성·삭제)

## 린트 부채 (init 시점 실측, 2026-07-31)

훅에 **비차단**으로 물려 있다 — 기존 코드를 건드리지 않기로 한 결정이다.

| 규칙 | 건수 | 성격 |
|---|---|---|
| `I001` unsorted-imports | 20 | 자동 수정 가능 |
| `B008` function-call-in-default-argument | 19 → **3** | 16건이 FastAPI `Depends()` 관용구였다 (실측). `pyproject.toml` 의 `extend-immutable-calls` 로 해소, 남은 3건은 진짜 |
| `F401` unused-import | 10 | 자동 수정 가능 |
| `BLE001` blind-except | 5 | 검토 대상 |
| `DTZ*` naive datetime | 6 | 검토 대상 |
| `S110` try-except-pass | 2 | 검토 대상 |

## 의존성 CVE 부채 (init 시점 실측, 2026-07-31)

13패키지 74건(고유 취약점 39건, Critical 2)이 `osv-scanner.toml` 에 사유와 함께
등재돼 있다. **등재된 건만 조용하고 새로 들어오는 취약 의존성은 pre-push 에서
그대로 막힌다** — 린트 부채를 비차단으로 내린 것과 같은 모양이다.

지금 올리지 않은 이유와 해소 순서는 `osv-scanner.toml` 머리말이 소유한다. 한 줄
요약: **이 레포의 테스트가 그 6개 패키지를 하나도 실행하지 않아 오라클이 없다.**

## 타입 부채 메모

pyright 25건 중 상당수는 SQLAlchemy async 세션 타이핑 artifact 다
(`Session` 이 `__aenter__` 를 노출하지 않음) — 라이브러리 스텁 문제이지 코드 결함이
아니다. 부채 정리는 `refactor/` 브랜치의 별도 과제이고, `.agents/context/debt.md`
가 대장을 갖는다.

## 없는 것 (그래서 선언적으로 스킵되는 검사)

- **alembic 마이그레이션 없음** → `30-migration.sh` 스킵
- **uv 아님(poetry)** → `40-supply-chain.sh` 의 PyPI 이름 환각 가드 스킵.
  의존성 CVE 스캔은 `osv-scanner` 가 생태계 무관으로 덮는다
- **CI 없음** → process-audit 은 로컬 실행에만 의존한다
- **커버리지 도구 없음** → 신규 코드 커버리지 게이트는 N/A
