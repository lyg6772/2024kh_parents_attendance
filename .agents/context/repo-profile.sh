# Repo profile: the ONLY repo-specific knobs the enforcement scripts read.
# This file is the portability boundary - scripts/ stay generic, this file is
# regenerated per repo (see .agents/PORTING.md). The audit FAILS CLOSED when
# this file is missing: without it, gate re-derivation would silently match
# nothing and the safety core would become a no-op.
#
# Required (audit exits hard if empty): SRC_DIR TESTS_DIR DEPS_MANIFEST
#   API_GATE_RE HIGH_RISK_PATH_RE HIGH_RISK_CONTENT_RE
# Optional (empty = that check is skipped, announced in the CI log):
#   MODELS_DIR MIGRATIONS_DIR SETTINGS_RE PKG_ECOSYSTEM SHARED_CODE_RE

SRC_DIR="app"
TESTS_DIR="tests"
DEPS_MANIFEST="pyproject.toml"

# added-line regex that marks an API surface change (FastAPI/Starlette routing).
# The identifier must END IN router/app rather than be anything at all, or
# `@mock.patch(` would trip the API gate on ordinary test diffs. Measured in
# this repo (2026-07-31): the live decorators are `@app.get`, `@app.exception_handler`
# and `@agent_router.post` - the second is why the verb list is not just the
# HTTP verbs. Adding a verb is cheap; a missed decorator skips the design gate.
API_GATE_RE="^\+.*(@[A-Za-z0-9_]*(router|app)\.(get|post|put|patch|delete|head|options|trace|websocket|websocket_route|route|api_route|exception_handler)\(|add_api_route|add_route|include_router|APIRoute\(|WebSocketRoute\(|Mount\()"

# paths where every change is high-risk (auth/authz, secrets/settings) -
# pre-approved patterns never apply here (team-policy 위험 차등 게이트).
# This repo keeps auth in app/util/auth.py (JWT + passlib/bcrypt), the DB
# session factory in app/util/db.py, and settings in app/config.py.
HIGH_RISK_PATH_RE="^app/util/auth\.py$|^app/util/db\.py$|^app/config\.py$"

# added-line vocabulary that flags payment/PII content (coarse on purpose -
# a hit only demands a human-gate record, not a redesign). Kept even though
# this repo has no payment surface today: the cost of a false positive is one
# recorded line, and the cost of adding it late is a missed gate.
HIGH_RISK_CONTENT_RE="^\+[^+].*(payment|billing|invoice|refund|card_number|결제|환불|카드번호|주민등록)"

# ORM 모델은 app/dao/tables.py 한 파일이고 전용 디렉토리가 없다. 처음엔 "디렉토리가
# 없으니 비워서 선언적으로 스킵" 으로 뒀는데, 그 선택의 결과가 더 나쁘다: lib.sh 가
# `grep -q "^$MODELS_DIR/"` 로 DB 스키마 게이트를 도출하므로 빈 값은 영구 no-op 이고,
# 이 레포의 ORM 실체를 바꾸는 feat 브랜치가 스키마 게이트를 하나도 안 건드린다 —
# 조용히 통과하는 방향이라 "선언적 스킵" 이라는 이름과 실제가 다르다.
#
# app/dao 로 켠다. 접두사 매치라 tables.py 가 잡히고, 대가는 같은 디렉토리의 쿼리
# 변경까지 게이트에 걸리는 노이즈다. ORM 정의와 쿼리가 한 디렉토리에 있는 한 그
# 노이즈는 이 레포의 구조가 지불하는 값이고, 놓친 스키마 변경보다 싸다.
MODELS_DIR="app/dao"
# alembic 없음 - 30-migration.sh 의 선형 히스토리 검사가 선언적으로 스킵된다
MIGRATIONS_DIR=""
SETTINGS_RE="^app/config\.py$"

# shared-code paths: a refactor/ branch touching these should carry fix-grade
# verification artifacts (team-policy 리팩토링 정책 — shadow device for now).
# 이 레포의 공유면은 util/ 전부와 dao/tables.py(모든 DAO 가 읽는 테이블 정의),
# service/models.py(계층 간 DTO)다.
SHARED_CODE_RE="^app/util/|^app/dao/tables\.py$|^app/service/models\.py$"
# python-uv enables the PyPI slopsquatting check (40-supply-chain.sh);
# any other value skips it - port the check when the ecosystem differs.
# 이 레포는 poetry 라 그 검사는 스킵된다. 의존성 CVE 스캔 자체는 osv-scanner 가
# 생태계 무관으로 덮으므로, 빠지는 것은 이름 환각(slopsquat) 가드뿐이다.
PKG_ECOSYSTEM="python-poetry"

# --- 영향 테스트 러너 (scripts/test_affected.sh) ---
# 커널 기본값은 맨 `pytest` 인데 이 레포 PATH 에 없다 (.venv/bin 이 안 잡힌다).
# **프로필이 이 값들의 유일한 소유자다.** 훅 env 에도 적으면 두 벌이 되고, 스크립트가
# 프로필을 나중에 source 하므로 훅 쪽이 조용히 무시된다 — 고칠 때 안 고쳐지는 사본이
# 생긴다. 프로필에 두면 `sh scripts/test_affected.sh` 직접 실행도 그대로 동작한다
# (실측 2026-08-01: 훅 env 에만 뒀을 때 직접 실행이 rc=127 로 죽었다).
FULL_SUITE_CMD="poetry run pytest -q --ignore=$TESTS_DIR/harness"
AFFECTED_RUNNER_CMD="poetry run pytest -q"
# 커널 기본값은 uv.lock·alembic 전제라 그대로 두면 poetry.lock 변경이 전체 스위트로
# 승격되지 않는다 — 조용히 통과하는 방향이다.
GLOBAL_EFFECT_RE='(^|/)conftest\.py$|^pyproject\.toml$|^poetry\.lock$'

# --- 골든 테스트 문 (scripts/test_affected.sh, 커널 0.25.0 신규) ---
# 하네스의 강제 코드는 어느 스택에서든 셸이고 그걸 심판하는 건 tests/harness/ 뿐인데,
# 코드 인덱스는 셸→테스트를 매핑하지 못한다. 그래서 SRC_EXT_RE(스택별 노브)를 타지
# 않고 전용 문으로 선다. 이 레포는 기본값이 그대로 맞다 — `scripts/` 는 전부 셸이고
# 골든 테스트도 설치돼 있다. 그래서 HARNESS_SRC_RE 는 안 적는다(기본값이 정답이면
# 적는 것이 곧 드리프트 지점을 하나 만드는 것이다).
#
# 러너만 스왑한다. 커널 기본값은 맨 `pytest` 인데 이 레포 PATH 에 없다 —
# FULL_SUITE_CMD·AFFECTED_RUNNER_CMD 와 같은 이유다. 경로는 리터럴로 박지 않고
# $TESTS_DIR 로 짠다: 위에서 이미 정의됐고, 나중에 테스트 경로를 옮겨도 같이 따라온다.
# (커널 프로필 템플릿은 이 줄을 아예 두지 말라고 하는데, 그건 리터럴 `tests/harness`
#  를 박는 경우를 막으려는 것이다. 러너 자체가 pytest 가 아닌 이 레포는 스왑 대상이고,
#  변수로 짜면 그 경고가 가리키는 파손은 생기지 않는다.)
HARNESS_SUITE_CMD="poetry run pytest -q $TESTS_DIR/harness"

# --- stop-validate (턴 종료 검증 훅 — moru 플러그인 scripts/stop_validate.sh) ---
# 파이프라인 밖 편집의 턴 종료 조기경보. 비우면 훅 전체 no-op (fail-open).
# 명령은 줄바꿈 구분, 각 줄이 sh -c 로 실행된다. 가볍게 유지 (매 편집 턴 실행됨).
#
# 이 레포는 기존 코드에 린트·타입 부채를 갖고 시작했다 (건수는 복제하지 않는다 —
# .agents/context/codebase-conventions.md 가 소유하고 재측정 명령을 함께 준다).
# 그 상태로 명령을 넣으면 매 턴 같은 지적이 다시 뜨고 신호가 죽는다. 그리고 훅은
# 편집한 파일 목록을 명령에 넘기지 않으므로(stop_validate.sh 는 sh -c "$cmd" 만
# 실행한다) "편집한 파일만 검사"는 여기서 표현할 수 없다 — 전부 아니면 전무다.
#
# 더 나쁜 것은 그 실패가 남기는 흔적이다: stop_validate 가 .stop-validate-failed
# 를 쓰고, pr_review_gate.sh 가 그 마커를 보면 같은 명령을 재실행해 여전히 빨간
# 것을 확인하고 푸시를 막는다. 부채가 있는 상태에서 여기를 채우면 모든 푸시가
# 영구히 차단된다.
#
# 그래서 비워 둔다 (훅 전체 no-op). pre-commit 의 ruff 훅이 편집 파일을 보긴 하지만
# `|| true` 라 **보고만 한다(비차단)** — 커버 강도가 다르다. 그러니 잃는 것은 턴 종료
# 조기경보 **와 차단력 둘 다**이고, 남는 차단층은 pre-push 게이트뿐이다. 부채가 0 이 되면 여기에
# `poetry run ruff check --quiet .` 를 넣는 것이 이 노브를 켜는 방법이다.
STOP_VALIDATE_CMDS=""
# dirty 마커에 기록할 파일 확장자 (기본: 주요 코드 확장자)
DIRTY_EXT_RE='\.py$'
