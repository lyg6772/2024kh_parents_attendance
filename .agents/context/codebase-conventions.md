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
| 린트 | `poetry run ruff check .` | **부채 있음** — 아래 "린트 부채" |
| 포맷 | `poetry run ruff format --check --diff .` | **부채 있음** — 아래 "린트 부채" |
| 타입 | `poetry run pyright app` | **부채 있음** — 아래 "린트 부채" |
| 테스트 | `poetry run pytest -q` | `testpaths = ["tests"]`, `asyncio_mode = "auto"` |
| e2e | `python run_app.py` 로 실기동 후 수동 확인 | 자동화된 e2e 스위트는 없다 — stage-6 은 수동 확인 결과를 기록한다 |
| 커버리지 | *(없음)* | 커버리지 도구 미설치 → **stage-6 §2-2 는 N/A 로 하강한다** |

## 테스트 규약

- 파일명 `tests/test_*.py`, 클래스로 묶는다 (`class TestArgsSchema:`)
- 테스트마다 주석으로 케이스 ID 를 단다 (`# P3-01: ...`) — 설계 문서의 요구사항과
  잇는 관용구다. 신규 테스트도 이 형식을 따른다
- async 테스트는 `asyncio_mode = "auto"` 라 데코레이터가 필요 없다
- DB 가 필요한 테스트는 `db_session` 픽스처를 받는다 (aiosqlite 인메모리,
  테이블은 매 테스트 생성·삭제)

## 린트 부채

훅에 **비차단**으로 물려 있다 — 기존 코드를 건드리지 않기로 한 결정이다.

**총계를 여기 적지 않는다.** init 중 이 숫자를 다섯 문서에 복제했다가 전부
어긋났다: 75 로 적었는데 `pyproject.toml` 에 규칙 선택(`select`)을 넣은 뒤 값이
바뀌었고, 그때는 이미 다섯 곳을 고쳐야 했다. 숫자는 규칙 선택·검사 범위·코드
변경에 따라 움직이므로 **문서가 아니라 명령이 소유한다.**

```bash
poetry run ruff check app          # 앱 코드만
poetry run ruff check .            # 앱 + 앱 자신의 tests/ (tests/harness 는
                                   # [tool.ruff] exclude 로 빠져 있다)
poetry run pyright app
```

성격만 기록한다 — 이건 안 움직인다:

| 규칙 | 성격 |
|---|---|
| `I001` unsorted-imports | 자동 수정 가능 |
| `F401` unused-import | 자동 수정 가능 |
| `B008` function-call-in-default-argument | 대부분 FastAPI `Depends()` 관용구였다 — `pyproject.toml` 의 `extend-immutable-calls` 로 해소했고, 남은 것은 진짜다 |
| `BLE001` blind-except | 검토 대상 |
| `DTZ*` naive datetime | 검토 대상 |
| `S110` try-except-pass | 검토 대상 |

**포맷 축은 검사 형태로만 돈다** (`--check --diff`). `06-verification.md` 가 이 표를
그대로 실행하는데, 변형 커맨드(`ruff format .`)를 두면 stage-6 이 미적용 파일을
전부 재작성한다 — `AGENTS.md`·`DEVELOPMENT.md` 의 "요청한 것만 수정, 관련 없는
리팩토링 금지"와 정면으로 충돌한다.

부채 대장은 아직 없다. `refactor/` 과제를 시작할 때 `.agents/context/debt.md` 를
만든다.

## 의존성 CVE 부채 (init 시점 실측, 2026-07-31)

설치 시점의 기존 취약점이 `osv-scanner.toml` 에 사유와 함께 등재돼 있다.
**등재된 건만 조용하고 새로 들어오는 취약 의존성은 pre-push 에서 그대로 막힌다** —
린트 부채를 비차단으로 내린 것과 같은 모양이다.

건수는 여기 적지 않는다(린트와 같은 이유 — 위 "린트 부채" 절). 현재 값은
`osv-scanner --recursive .` 로 재측정하고, 등재 목록 자체는 `osv-scanner.toml` 이
소유한다.

지금 올리지 않은 이유와 해소 순서는 `osv-scanner.toml` 머리말이 소유한다. 한 줄
요약: **이 레포의 테스트가 그 6개 패키지를 하나도 실행하지 않아 오라클이 없다.**

## SAST 부채 (init 시점 실측, 2026-07-31)

semgrep 지적 **1건**: `Dockerfile` 에 `USER` 지시가 없어 컨테이너가 root 로 돈다
(`dockerfile.security.missing-user`). 훅은 기본 브랜치와의 merge-base 를 기준선으로
써서 이 건을 아래로 내리고 **이 브랜치가 새로 만든 지적만** 막는다.

고치려면 `USER` 를 추가하면 되지만 컨테이너 안 파일 권한이 바뀌어 앱이 깨질 수
있다 — 실기동으로 확인해야 하는 변경이라 하네스 설치 PR 의 범위 밖이다. 후속 과제.

## 타입 부채 메모

pyright 지적의 상당수는 SQLAlchemy async 세션 타이핑 artifact 다 (`Session` 이
`__aenter__` 를 노출하지 않음) — 라이브러리 스텁 문제이지 코드 결함이 아니다.
부채 정리는 `refactor/` 브랜치의 별도 과제다.

## 없는 것 (그래서 선언적으로 스킵되는 검사)

- **alembic 마이그레이션 없음** → `30-migration.sh` 스킵
- **uv 아님(poetry)** → `40-supply-chain.sh` 의 PyPI 이름 환각 가드 스킵.
  의존성 CVE 스캔은 `osv-scanner` 가 생태계 무관으로 덮는다
- **GitHub 워크플로우 없음** → 커널 문서 여러 곳이 "CI 의 process-audit" 이라고
  부르는 백스톱을 `.pre-commit-config.yaml` 의 pre-push 훅으로 옮겨 배선했다.
  실제로 돌지만 **서버측 강제력은 없다** — 훅을 지운 사람은 우회할 수 있고, 그
  층은 PR 리뷰가 대신한다. 문서에서 "CI" 라고 읽히는 곳은 이 훅으로 해석한다
- **커버리지 도구 없음** → 신규 코드 커버리지 게이트는 N/A
