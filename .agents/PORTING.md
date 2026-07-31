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
| `scripts/process_audit.sh` + `scripts/audit/*.sh` | 감사 골격 (레포 특화 값은 전부 프로필에서 읽음) |
| `scripts/test_lock_check.sh`, `scripts/test_lock_guard.sh`, `scripts/unlock_tests.sh` | LOCK 강제 3층 |
| `scripts/device_telemetry.sh` | 장치 적중 **기록**. 예외적으로 테스트는 함께 오지 않는다 — `tests/device_telemetry_matrix.sh` 는 기록기의 fail-open 계약(=클래스 속성)을 검증하므로 플러그인에 남는다. (보고 전용, 게이트 결과에 영향 없음). 읽기는 플러그인의 `scripts/telemetry_report.py` 가 하므로 커널에는 기록기만 온다 — `/doctor` 또는 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/telemetry_report.py"` 로 집계 |
| `scripts/pr_review_gate.sh`, `scripts/default_branch.sh` | 푸시 전 LLM 리뷰 게이트 |
| 보안 바닥 훅 (gitleaks·semgrep·osv-scanner) | 언어무관 — precommit 체인에서 그대로 복사, 스택별 스왑 안 함 (도구만 설치) |
| `tests/harness/` | 강제 스크립트 골든 테스트 (스크립트를 가져가면 테스트도 가져간다) |
| `.claude/commands/*.md` + `.claude/agents/*.md` | 커맨드·서브에이전트 (모델 티어링 포함) |

## 레포마다 재생성하는 것 (셸)

| 대상 | 방법 |
|------|------|
| **`.agents/context/repo-profile.sh`** | **필수 — 없으면 감사가 하드 레드.** 소스 경로, 테스트 경로, 의존성 매니페스트, API 게이트 정규식, 고위험 경로/어휘 정규식, 마이그레이션 경로, 패키지 생태계. 파일 안 주석이 스펙이다 |
| `.agents/context/codebase-conventions.md` | 새 레포의 패턴으로 재생성 (기존 규약 — 파일 헤더 참조) |
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

- `scripts/test_lock_guard.sh`의 Bash 쓰기 탐지 정규식은 `tests/` 경로를 하드코딩한다
  — 테스트 경로가 다르면 스크립트 내 정규식도 수정 (best-effort 층이라 놓쳐도
  pre-commit 훅이 백스톱).
- `scripts/test_affected.sh`의 러너·전역효과 파일은 python/pytest가 **기본값**이고
  knob으로 스왑한다 (`FULL_SUITE_CMD`, `AFFECTED_RUNNER_CMD`, `GLOBAL_EFFECT_RE`,
  `SRC_EXT_RE` — 스크립트 헤더가 스펙). `AFFECTED_TESTS_CMD`의 `test_*.py` 필터도
  테스트 네이밍 규약에 맞게 함께 스왑.
- `.pre-commit-config.yaml`의 `junk-comments` 정규식은 python/`#`-주석 관용구가
  기본값 — 스택별 디버그 관용구(예: JS `debugger;`)로 스왑 (훅 자체는 커널).
- `scripts/audit/40-supply-chain.sh`(신규 의존성 PyPI slopsquat/typosquat 가드)는
  python-uv 전용 — 다른 생태계는 프로필의 `PKG_ECOSYSTEM`을 바꾸면 **선언적으로
  스킵**되며, 동등한 이름-환각 검사를 원하면 포팅 필요. (의존성 CVE 스캔 자체는
  osv-scanner로 생태계 무관 — 이 한계는 이름 환각 가드에만 해당.)
- `scripts/audit/30-migration.sh`의 선형 히스토리 검사는 Alembic 전제 —
  `MIGRATIONS_DIR`가 비면 스킵된다.

## 이식 절차 (체크리스트)

1. 커널 복사 → `repo-profile.sh` 작성 → 골든 테스트 실행 (`pytest tests/harness`)
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
