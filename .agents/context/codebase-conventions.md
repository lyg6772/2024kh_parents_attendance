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

훅 체인은 `poetry` 밖의 바이너리 셋에 의존한다 — `gitleaks`(비밀 스캔) ·
`semgrep`(SAST) · `osv-scanner`(의존성 CVE). 셋 다 pre-push 를 **차단**하므로, 없으면
새 클론에서 푸시가 막힌다. macOS 는 `brew install gitleaks semgrep osv-scanner`,
그 외는 각 프로젝트의 릴리스 바이너리를 쓴다. `gh`(PR 조회)와 `claude`(리뷰 게이트)는
없어도 해당 층이 비차단으로 내려갈 뿐이라 필수는 아니다.

## 테스트 규약

- 파일명 `tests/test_*.py`, 클래스로 묶는다 (`class TestArgsSchema:`)
- 테스트마다 주석으로 케이스 ID 를 단다 (`# P3-01: ...`) — 설계 문서의 요구사항과
  잇는 관용구다. 신규 테스트도 이 형식을 따른다
- async 테스트는 `asyncio_mode = "auto"` 라 데코레이터가 필요 없다
- DB 가 필요한 테스트는 `db_session` 픽스처를 받는다 (aiosqlite 인메모리,
  테이블은 매 테스트 생성·삭제)

## 숨은 결합

*(아직 없음 — 발견할 때마다 여기 append 한다. 지우지 않는다.)*

파이프라인이 **이름으로 지목하는 레지스트리**다: `02-feature-analysis.md` §5 가 영향 맵
밖의 결합을 여기서 찾고, `07-review.md` 가 finder 컨텍스트로 넣고 발굴한 것을 여기
올린다. 비어 있어도 섹션은 있어야 한다 — 없으면 append 할 자리가 없다.

한 줄 형식: `무엇 ↔ 무엇` · 왜 안 보이나 · 어디서 드러났나.

| 결합 | 왜 안 보이나 | 발견 경위 |
|---|---|---|
| *(비어 있음)* | | |

## 인프라 컨텍스트

`03-design.md` §0-2 가 설계 전에 읽는다 — 설계가 없는 인프라를 전제하지 않도록.

| | |
|---|---|
| 실행 형태 | 단일 프로세스 uvicorn. `python run_app.py` 로 기동 |
| 컨테이너 | `Dockerfile` 있음. 오케스트레이터 없음 (k8s·compose 미사용) |
| DB | 운영 Oracle, 로컬/테스트 SQLite. 마이그레이션 도구 없음 — 스키마 변경은 수작업 |
| 캐시·큐·오브젝트 스토리지 | **없다.** 필요하면 그것부터 도입 결정이 선행한다 |
| 외부 API | Groq(primary) · Gemini(fallback). 그 외 신규 외부 의존은 사람 승인 대상 |
| 비밀 관리 | `app/.env` (gitignored). 시크릿 매니저 없음 |
| 관측 | 구조화 로깅·메트릭·트레이싱 **없음.** 장애 진단은 서버 로그 직접 확인 |
| CI | **없다.** 게이트는 로컬 pre-push 훅뿐 — 아래 "없는 것" 절이 소유한다 |

**금지**: 여기 없는 인프라를 설계가 전제하면 그건 설계가 아니라 요청이다. 스테이지 3
결정 로그에 "이 인프라가 필요하다"를 사람 결정 항목으로 올린다.

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

**자동 수정 커맨드는 이 레포에 없다.** `06-verification.md` 의 실패 라우팅 표가
"린트 에러 → 자동 수정 (conventions 의 lint fix 커맨드)" 라고 하지만, 여기에 그
커맨드를 두지 않는 것이 결정이다 — 기존 부채가 있는 상태에서 `ruff check --fix` 는
이번 작업과 무관한 파일까지 고쳐 같은 규칙을 어긴다. stage-6 은 자동 수정 대신
**지적을 보고하고 사람 판단으로 넘긴다.**

## 골든 테스트 (하드월의 유일한 증거)

`tests/harness/` 는 강제 스크립트의 골든 테스트다. **전건 green 이고 기본 수집에
들어 있다** — red 는 회귀로 판정한다 (`.agents/PORTING.md` § 이식 절차 1번, 환경 예외
2건 포함). 재측정: `poetry run pytest tests/harness -q`.

`sh scripts/process_audit.sh` PASS 로 대신할 수 없다. 그 스크립트는
`scripts/audit/[0-9]*-*.sh` 만 돌아서 **LOCK 가드·기본 브랜치 보호·영향 테스트 선택을
전혀 실행하지 않는다.** 그 셋의 살아 있음을 확인하는 자리가 여기뿐이다.

> init 시점(2026-07-31)에는 12건이 빨개서 기본 수집에서 빼 두었고 실패 파일 내역을
> 여기 적었다. 그 red 는 이 레포의 결함이 아니라 커널 픽스처가 자기 프로필 대신
> **이 레포의** 프로필을 읽은 결과였다. moru 쪽에서 결합을 끊어(커널 0.24.1) 12건이
> 사라졌으므로, 그 표는 기록할 대상이 없어 지웠다.

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
  **열린 PR 이 있는 브랜치에서만 돈다** — 이 감사는 완성된 브랜치를 보는 검사라
  작업 중에 돌리면 반드시 hard-fail 한다(사유는 그 훅의 주석이 소유한다).
  실제로 돌지만 **서버측 강제력은 없다** — 훅을 지운 사람은 우회할 수 있고, 그
  층은 PR 리뷰가 대신한다. 문서에서 "CI" 라고 읽히는 곳은 이 훅으로 해석한다.
  이 레포는 public 이라 Actions 무료 분 제한에 걸리지 않는다 — 워크플로우를 안 둔
  것은 비용 판단이 아니다. 나중에 서버측 강제력이 필요하면 그때 넣으면 된다.
  **`.agents/team-policy.md` § 머지 규칙이 요구하는 required status check 두 개는
  이 레포에 없다**: `process-audit` 은 위처럼 pre-push 훅으로 해석하고, `quality`
  (린트·타입·테스트)는 대응물이 `.pre-commit-config.yaml` 의 ruff·pytest 훅인데
  **ruff 는 비차단**이라 등가가 아니다. 즉 머지 규칙이 전제하는 서버측 차단은 이
  레포에 존재하지 않으며, 그 층은 사람의 PR 리뷰가 대신한다. 커널 문서를 고쳐
  맞추지 않는 이유는 그게 커널 사본이기 때문이다 (`.agents/PORTING.md`) — 레포별
  이탈은 여기서 선언한다
- **커버리지 도구 없음** → 신규 코드 커버리지 게이트는 N/A
- **커널이 `.github/PULL_REQUEST_TEMPLATE.md` 를 출하하지 않는다** → 대상 레포는
  `scripts/pr_body_check.sh` 는 받지만 대조할 파일은 못 받는다. 아무도 템플릿을 만들지
  않으면 이 층은 켜져 있는 것처럼 보이면서 아무것도 안 본다. 이 레포는 원천 레포의
  템플릿을 바탕으로 §설계 산출물을 더해 메웠다 — `.agents/team-policy.md` § PR 생성
  규칙이 요구하는 네 항목 중 셋만 원본이 덮고, 설계 산출물 링크는 원천이 단계 파이프라인을
  안 돌려 없기 때문이다. **자동 동기화 장치는 없다**: 원천 템플릿이 바뀌어도 여기는 안
  따라오고, 요구 항목의 소유자는 `.agents/team-policy.md` 다. 커널 사본을 고쳐 맞추지 않는
  이유는 그게 커널 사본이기 때문이다 (`.agents/PORTING.md`) — 원천(moru) 쪽 후속이다
- **PR 생성 시점에는 이 층이 여전히 안 돈다** → 훅은 *열린 PR 이 있는 푸시* 에서만
  대조하는데 PR 생성은 푸시가 아니다. 생성 직후 `sh scripts/pr_body_check.sh <N>` 을
  한 번 직접 부르는 것이 그 구멍을 메우는 유일한 경로이고, 두 번째 푸시부터는 훅이 본다.
  process-audit 훅이 같은 이유로 갖는 잔여 위험과 같은 모양이다
