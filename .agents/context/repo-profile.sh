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

# ORM 모델은 dao/tables.py 한 파일에 모여 있어 디렉토리가 아니다. 디렉토리를
# 요구하는 검사이므로 비워 선언적으로 스킵한다 - 잘못된 경로를 적으면 그 검사가
# 조용히 아무것도 안 잡는다.
MODELS_DIR=""
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

# --- stop-validate (턴 종료 검증 훅 — moru 플러그인 scripts/stop_validate.sh) ---
# 파이프라인 밖 편집의 턴 종료 조기경보. 비우면 훅 전체 no-op (fail-open).
# 명령은 줄바꿈 구분, 각 줄이 sh -c 로 실행된다. 가볍게 유지 (매 편집 턴 실행됨).
#
# 실측 2026-07-31 (init 시점): 기존 코드에 ruff 75건 · pyright 25건이 걸려 있다.
# 그 상태로 여기 넣으면 매 턴 같은 100건이 뜨고 신호가 죽으므로, 편집한 파일만
# 보는 ruff 만 둔다. pyright 는 부채가 정리된 뒤 추가한다.
STOP_VALIDATE_CMDS="poetry run ruff check --quiet ."
# dirty 마커에 기록할 파일 확장자 (기본: 주요 코드 확장자)
DIRTY_EXT_RE='\.py$'
