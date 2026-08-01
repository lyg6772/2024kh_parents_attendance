# PORTING — 이 하네스를 다른 레포로 이식하기

이 하네스는 **이식 가능한 커널**과 **레포별 재생성 셸**로 나뉜다.
커널은 그대로 복사하고, 셸은 새 레포에서 다시 만든다.
셸을 빼먹으면 감사가 **fail-closed로 레드**가 난다 (조용한 무력화 방지 —
`scripts/audit/lib.sh`가 `repo-profile.sh` 부재 시 하드 실패).

## 그대로 복사하는 것 (커널)

| 대상 | 내용 |
|------|------|
| `.agents/workflow.md`, `00-*.md`~`07-*.md` | 파이프라인 헌법 + 단계 파일 (스택 중립 ~90%) |
| `.agents/team-policy.md` | 운영 규칙 (고위험 경로 이름만 프로필로 이동됨) |
| `.agents/collaboration.md` | 사용자/팀 working-style 프로필 (빈 스캐폴드 — AI가 관찰 append) |
| `.agents/QUICKSTART.md`, 이 파일 | 온보딩 |
| `.agents/context/` 디렉토리 계약 | `decisions/` `artifacts/` `locks/` 구조 |
| `.agents/context/test-taxonomy.md` | 테스트 taxonomy 루브릭 — `04-test-generation.md` 와 `/gen-tests` 가 **이름으로 지목**한다. 커널 문서 표의 `.agents/*.md` 는 하위 디렉토리를 안 덮으므로 별도 행이다 |
| `.agents/context/codebase-conventions.md` | **스캐폴드로 복사한 뒤 내용만 채운다** (아래 재생성 표의 같은 행이 채우는 법을 소유한다). 같은 이유로 별도 행이고, `##` 섹션 이름은 스테이지들이 이름으로 지목하므로 지우지 않는다 |
| `scripts/process_audit.sh` + `scripts/audit/*.sh` | 감사 골격 (레포 특화 값은 전부 프로필에서 읽음) |
| `scripts/test_lock_check.sh`, `scripts/test_lock_guard.sh`, `scripts/unlock_tests.sh` | LOCK 강제 3층 |
| `scripts/device_telemetry.sh` | 장치 적중 **기록**. 예외적으로 테스트는 함께 오지 않는다 — `tests/device_telemetry_matrix.sh` 는 기록기의 fail-open 계약(=클래스 속성)을 검증하므로 플러그인에 남는다. (보고 전용, 게이트 결과에 영향 없음). 읽기는 플러그인의 `scripts/telemetry_report.py` 가 하므로 커널에는 기록기만 온다 — `/doctor` 또는 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/telemetry_report.py"` 로 집계 |
| `scripts/pr_review_gate.sh`, `scripts/default_branch.sh` | 푸시 전 LLM 리뷰 게이트 |
| `scripts/protect_default_branch.sh`, `scripts/pr_body_check.sh`, `scripts/test_affected.sh` | 나머지 pre-push 층 — 기본 브랜치 직접 푸시 차단 · PR 본문 템플릿 준수 · 영향 테스트 선택. **셸 체인이 이것들을 배선하므로 빼면 훅이 실체 없이 남는다** |
| 보안 바닥 훅 (gitleaks·semgrep·osv-scanner) | 언어무관 — precommit 체인에서 그대로 복사, 스택별 스왑 안 함 (도구만 설치) |
| `tests/harness/` | 강제 스크립트 골든 테스트 (스크립트를 가져가면 테스트도 가져간다) |
| ~~`.claude/commands/*.md` + `.claude/agents/*.md`~~ (source-repo-only: 복사하지 말라고 경로를 지목하는 행이라 인용 검사에서 면제한다) | **복사하지 않는다 — moru 플러그인이 제공한다.** 커맨드·서브에이전트(모델 티어링 포함)는 플러그인이 설치된 세션에서 그대로 뜨므로, 복사하면 두 벌이 생기고 갱신이 갈라진다. 실측 2026-07-31: 대상 레포에 `.claude/` 가 하나도 없이 슬래시 커맨드 전부와 `test_lock_guard.sh` 의 PreToolUse 훅이 동작했다. 플러그인 없이 하네스만 쓰려면 **설치 시점(플러그인이 있는 세션)에** `${CLAUDE_PLUGIN_ROOT}/commands/` · `${CLAUDE_PLUGIN_ROOT}/agents/` 에서 미리 복사해 둔다 — 그 변수는 플러그인이 있을 때만 정의되므로 나중에는 풀리지 않는다 |

## 레포마다 재생성하는 것 (셸)

| 대상 | 방법 |
|------|------|
| **`.agents/context/repo-profile.sh`** | **필수 — 없으면 감사가 하드 레드.** 소스 경로, 테스트 경로, 의존성 매니페스트, API 게이트 정규식, 고위험 경로/어휘 정규식, 마이그레이션 경로, 패키지 생태계. 파일 안 주석이 스펙이다 |
| `.agents/context/codebase-conventions.md` | 커널이 **스캐폴드를 함께 보낸다** — 그 파일의 `##` 섹션을 이 레포 값으로 채운다. **섹션 이름을 지우지 않는다**: `02-feature-analysis.md` §5 와 `07-review.md` 가 "숨은 결합" 을, `03-design.md` §0-2 가 "인프라 컨텍스트" 를 **이름으로 지목**하므로, 없으면 그 단계들이 존재하지 않는 자리에 append 하라는 지시를 받는다 (실측 2026-08-01, 2차 포팅) |
| `.agents/context/pre-approved-patterns.md` | 빈 상태로 시작, 사람이 등록 |
| 레포 `.gitignore` | `.agents/context/telemetry/` 와 런타임 마커(`.stop-dirty`, `.stop-validate-running`, `.stop-validate-failed`, `.pipeline-active`)를 추가 — 머신 로컬 상태다. 빼먹으면 `devices.jsonl` 이 커밋에 섞인다 |
| `docs/adr/` | 빈 현황판으로 시작 (README의 규칙·형식은 커널 — 그대로 복사) |
| `docs/OVERVIEW.md` | 제품 큰그림 맵 — 스택 감지 + 발굴 패스로 시드 (형식: `templates/docs/OVERVIEW.md`); "현재 방향"은 결정 로그서 갱신 |
| `AGENTS.md` (또는 CLAUDE.md) | 새 레포의 스택/규칙/빌딩블록으로 재작성 |
| `.opencode/skills/` 도메인 스킬 + `.claude/skills/` 스텁 | 스택이 다르면 재작성 (FastAPI/SQLAlchemy 전제) |
| `.pre-commit-config.yaml` | 훅 체인 유지. **보안 바닥(gitleaks·semgrep·osv-scanner)은 언어무관이라 그대로**, **품질 도구(ruff/pyright/uv-lock)만** 스택 커맨드로 스왑. `test-lock` 훅의 `files: ^tests/` 패턴이 테스트 경로 knob |
| `.github/workflows/ci.yml` | quality 잡의 커맨드 교체. process-audit 잡은 그대로 |
| `cto-reviewer.md`의 프로브 판정 기준 | 스택 결합 잔여는 authz 프로브의 HTTP 응답 기준(401/403/404)과 pytest 예시뿐(예시 표기 + conventions 위임됨). HTTP가 아닌 인터페이스 표면이면 프로브 판정 기준만 스택에 맞게 |
| `06-verification.md`가 참조하는 검증/e2e/**커버리지** 커맨드 | conventions "검증 커맨드" 섹션에 새로 정의 (커버리지 도구 없으면 그 사실을 적어 6단계가 N/A로 하강) |

## 알려진 한계 (이식 시 확인)

- `scripts/test_lock_guard.sh`의 Bash 쓰기 탐지 정규식은 `tests/` 경로를 하드코딩한다.
  **테스트 경로가 다르면 이 편집 시점 층은 inert 다 — 고치지 않는다.** 스크립트
  자신의 KNOWN LIMIT 이 그렇게 선언하고(`test_lock_guard.sh` 머리말), 커밋 시점 훅과
  감사가 백스톱이다. 굳이 고치면 `test_lock_guards.py` 의 경로 케이스가 정상 red 가
  되는데, 위 § 이식 절차 1번은 red 를 회귀로 판정하므로 포터가 유령을 쫓는다.
  (2026-08-01 정정: 이전에는 "정규식도 수정"이라고 지시해 스크립트 선언과 어긋났다.)
- `scripts/test_affected.sh`의 러너·전역효과 파일은 python/pytest가 **기본값**이고
  knob으로 스왑한다 (`FULL_SUITE_CMD`, `AFFECTED_RUNNER_CMD`, `GLOBAL_EFFECT_RE`,
  `SRC_EXT_RE` — 스크립트 헤더가 스펙). `AFFECTED_TESTS_CMD`의 `test_*.py` 필터도
  테스트 네이밍 규약에 맞게 함께 스왑.
  **`HARNESS_SRC_RE`·`HARNESS_SUITE_CMD` 는 스택 스왑 대상이 아니다** — 하네스의 강제
  코드는 어느 스택에서든 셸이고 `tests/harness/` 가 그 유일한 심판이라, 이 문만 별도로
  선다. 두 경우에만 손댄다: 강제 스크립트를 `scripts/` 밖에 뒀으면 정규식을 맞추고
  (안 맞으면 조용히 옛 fail-open 이다), 골든 테스트를 안 가져왔으면 `HARNESS_SRC_RE=""`
  로 끈다. 값은 `repo-profile.sh` 의 같은 이름 절이 소유한다.
- `.pre-commit-config.yaml`의 `junk-comments` 정규식은 python/`#`-주석 관용구가
  기본값 — 스택별 디버그 관용구(예: JS `debugger;`)로 스왑 (훅 자체는 커널).
- `scripts/audit/40-supply-chain.sh`(신규 의존성 PyPI slopsquat/typosquat 가드)는
  python-uv 전용 — 다른 생태계는 프로필의 `PKG_ECOSYSTEM`을 바꾸면 **선언적으로
  스킵**되며, 동등한 이름-환각 검사를 원하면 포팅 필요. (의존성 CVE 스캔 자체는
  osv-scanner로 생태계 무관 — 이 한계는 이름 환각 가드에만 해당.)
- `scripts/audit/30-migration.sh`의 선형 히스토리 검사는 Alembic 전제 —
  `MIGRATIONS_DIR`가 비면 스킵된다.

## 이식 절차 (체크리스트)

1. 커널 복사 → `repo-profile.sh` 작성 → 골든 테스트 실행 (`pytest tests/harness`).
   **전부 green 이어야 한다. red 는 회귀다** — 이 스위트는 이 레포의 프로필을 읽지
   않는다. `conftest.py` 가 합성 레포의 프로필을 리터럴로 들고 있어서, 대상 레포의
   스택·레이아웃과 무관하게 같은 입력으로 돈다. 판정할 것은 하나다: **`scripts/` 를
   제대로 복사했는가.** (프로필이 다르면 `test_audit_*` red 가 정상이라던 이전 규칙은
   2026-08-01 에 폐기됐다 — 그 관용이 오탐만 만들었기 때문이고, 근거는
   `conftest.py` 의 `REPO_PROFILE` 머리주석이 이 레포 안에서 소유한다.)

   **단 두 가지는 회귀가 아니라 환경이므로 먼저 배제한다:** ① 수집 에러 —
   `test_audit_supply_chain.py` 가 `from datetime import UTC` 를 쓰므로 python 3.11
   미만이면 그 파일만 임포트에서 죽는다(나머지는 돈다),
   ② 러너 설정 — `pyproject.toml` 의 `addopts` 에 커버리지 임계나
   `filterwarnings = ["error"]` 가 있으면 `pytest tests/harness` 단독 실행이 그것 때문에
   빨개진다. 그 밖은 전부 밀폐돼 있다(git 설정 격리·가짜 curl·jq 없으면 skipif).

   그래서 `sh scripts/process_audit.sh` PASS 는 감사 체인이 정상이라는 뜻일 뿐,
   하드월이 살아 있다는 증거가 아니다 — `process_audit.sh` 는 `scripts/audit/[0-9]*-*.sh`
   만 돌므로 LOCK 가드·기본 브랜치 보호·영향 테스트 선택은 **전혀 실행하지 않는다.**
   그 셋의 유일한 증거가 이 스위트다. **포팅 보고에 실패한 파일 이름을 적는다.**
2. 셸 항목 재생성 (위 표 순서대로)
3. 첫 기능을 QUICKSTART 해피패스로 1회 돌려 게이트·LOCK·감사가 실제로 발화하는지 확인
4. `장치 적중` 텔레메트리를 기능 5~10개 누적 후 검토 — **돌았는데도** 적중 0인 장치는
   강등 후보. 모든 칸이 0인 행은 아니다: 그건 기록기가 여기서 한 번도 돌지 않았다는
   뜻(훅 off, 또는 그 장치까지 도달한 적이 없음)이고, 그걸 근거로 강등하면
   **측정된 적 없는 장치를 지운다**.
   리포트가 그 둘을 다른 문구로 구분한다.
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/telemetry_report.py"` 또는 `/doctor` 로 본다.
   `fire`=위반 검출, `pass`=돌았고 통과, `n/a`=평가했으나 해당 없음,
   `skip`=평가 자체를 안 함(프로필 off 또는 평가 전 사람 우회), `degraded`=돌았으나 온전치 않게, `unavailable`=도구 부재.
   `audit:*` 는 주로 CI(PR)에서 돌고 러너 체크아웃은 일회성이라 로컬에는 대개
   안 남는다 (로컬에서 `process_audit.sh` 를 직접 돌리면 기록된다). 기록기는
   파일에만 append 하므로 CI 로그에도 안 보인다 — CI 쪽 적중은 지금은
   `say FAIL` 라인으로만 확인 가능하다 (아티팩트 업로드 미구현).
   `n/a`·`skip`·`unavailable` 은 통과가 아니다 — 첫 실이식(2026-07-26)에서 장치 ~15개 중 3개만
   실제 값을 냈다는 것이 이 계측기를 만든 계기다.
