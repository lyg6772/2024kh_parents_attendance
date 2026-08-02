#!/bin/sh
# Inner-loop accelerator: run only the tests affected by current changes,
# resolved through a code-index tool. The pre-push hook runs this selector;
# CI is the authority that always runs the full suite. Fail-closed: with changes
# in hand, every uncertain path (no index, sync failure, query miss, global-effect
# file changed) falls back to the FULL suite, so it is faster but never weaker.
# "No changes at all" exits 0 before that - there is nothing to be uncertain about.
#
# The index tool AND the stack values are pluggable (python/pytest defaults).
# Override via env or .agents/context/repo-profile.sh:
#   INDEX_MARKER        file whose presence means "an index exists"
#   INDEX_SYNC_CMD      refresh the index (exit != 0 => full suite)
#   AFFECTED_TESTS_CMD  changed source files on stdin -> affected test files
#   TESTS_DIR           test root (default tests)
#   SRC_EXT_RE          source-file extension regex (default \.py$)
#   GLOBAL_EFFECT_RE    files whose change always escalates to the full suite
#   TEST_FILE_RE        test-file naming regex (default python test_*.py)
#   FULL_SUITE_CMD      full-suite runner (default pytest, harness dir excluded —
#                       the goldens have their own door, see HARNESS_SRC_RE)
#   AFFECTED_RUNNER_CMD runner for the selected test files (default pytest)
#   HARNESS_SRC_RE      the harness's own shell code, which no index maps to tests
#                       (default ^scripts/.*\.sh$; empty = opt out). Changing it
#                       runs HARNESS_SUITE_CMD before the normal selection.
#   HARNESS_SUITE_CMD   the golden tests (default pytest -q $TESTS_DIR/harness)
set -u

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$(git rev-parse --show-toplevel)" || exit 1

[ -f .agents/context/repo-profile.sh ] && . .agents/context/repo-profile.sh
INDEX_MARKER=${INDEX_MARKER:-.codegraph/codegraph.db}
INDEX_SYNC_CMD=${INDEX_SYNC_CMD:-"codegraph sync -q"}
TESTS_DIR=${TESTS_DIR:-tests}
SRC_EXT_RE=${SRC_EXT_RE:-'\.py$'}
# The harness's own enforcement code is SHELL in every repo whatever the stack, and
# tests/harness/ is the only thing that referees it - no code index maps shell to
# those tests. So it gets its own pair of knobs rather than riding SRC_EXT_RE: a
# stack swapping SRC_EXT_RE to `\.go$` would otherwise silently drop it again.
# Empty HARNESS_SRC_RE opts out (a repo that did not take the golden tests).
# Set HARNESS_SRC_RE in the profile if the enforcement scripts live outside
# `scripts/` - an unmatched regex is the old fail-open, silently.
# `-`, not `:-`: an explicitly EMPTY value must opt out. With `:-` the empty
# string falls back to the default, so the documented opt-out silently did the
# opposite of what it said (caught by its own golden test).
HARNESS_SRC_RE=${HARNESS_SRC_RE-'^scripts/.*\.sh$'}
HARNESS_SUITE_CMD=${HARNESS_SUITE_CMD:-"pytest -q $TESTS_DIR/harness"}
TEST_FILE_RE=${TEST_FILE_RE:-'(^|/)test_[^/]+\.py$'}
GLOBAL_EFFECT_RE=${GLOBAL_EFFECT_RE:-'(^|/)conftest\.py$|^pyproject\.toml$|^uv\.lock$|^alembic\.ini$|^migrations/'}
FULL_SUITE_CMD=${FULL_SUITE_CMD:-"pytest -q --ignore=$TESTS_DIR/harness"}
AFFECTED_RUNNER_CMD=${AFFECTED_RUNNER_CMD:-"pytest -q"}
AFFECTED_TESTS_CMD=${AFFECTED_TESTS_CMD:-"codegraph affected --stdin -q -f '$TESTS_DIR/test_*.py'"}

# The goldens referee the harness's own SHELL, which no code index maps to tests,
# so they get their own door rather than riding the source path. Runs at most once
# per invocation: `full()` calls it too, for the escalations that happen before we
# know what changed.
_goldens_ran=0
run_goldens() {
  [ "$_goldens_ran" = 1 ] && return 0
  [ -n "${HARNESS_SRC_RE:-}" ] || return 0
  # A repo that skipped tests/harness at install (no pytest) has no goldens to run.
  # Without this guard the door would `pytest -q tests/harness` into a missing path
  # and hard-block every push touching scripts/ - the opt-out is documented in the
  # profile, but a wrong default must not need reading to survive.
  if [ ! -d "$TESTS_DIR/harness" ]; then
    # 조용히 돌아가지 않는다 — 선언되지 않은 부재는 조용한 통과와 구별되지 않는다.
    echo "test_affected: $TESTS_DIR/harness 없음 — 골든 테스트 건너뜀 (설치 때 안 가져왔다면 프로필의 HARNESS_SRC_RE 를 비운다)" >&2
    sh "$script_dir/device_telemetry.sh" test-affected unavailable "no $TESTS_DIR/harness" 2>/dev/null || :
    return 0
  fi
  _goldens_ran=1
  echo "test_affected: $1 — running the golden tests ($TESTS_DIR/harness)" >&2
  sh -c "$HARNESS_SUITE_CMD"
  _rc=$?
  # record the OUTCOME, not the attempt: logging before the run makes a golden
  # failure indistinguishable from a pass in the telemetry.
  [ "$_rc" = 0 ] && _ev=pass || _ev=fire
  sh "$script_dir/device_telemetry.sh" test-affected "$_ev" "harness-source" 2>/dev/null || :
  [ "$_rc" = 0 ] || exit "$_rc"
}

# The full-suite fallback still excludes tests/harness, and that stays correct:
# this is the fallback for SOURCE changes, and the goldens referee shell, not the
# stack's source. Folding them in would charge every index-less repo ~2-3 minutes
# on EVERY push - those repos always land here - for a class the door covers.
# But when we get here without knowing what changed (no diff base — the index check
# now sits below `changed=`, so it is not one of these), we
# cannot rule out a gate edit, so the door opens: unknown is fail-closed.
full() {
  [ -z "${changed+x}" ] && run_goldens "$1, so the changed set is unknown"
  sh "$script_dir/device_telemetry.sh" test-affected degraded "fallback-full: $1" 2>/dev/null || :
  echo "test_affected: $1 — running full suite" >&2
  # shellcheck disable=SC2086
  exec $FULL_SUITE_CMD
}

# fail-closed: without a diff base, committed branch work would look like "no
# changes" and skip tests entirely — escalate to full instead
base=$(sh "$script_dir/default_branch.sh" 2>/dev/null) || full "cannot resolve default branch"
merge_base=$(git merge-base HEAD "$base" 2>/dev/null) || full "cannot compute merge-base"

changed=$(
  {
    git diff --name-only "$merge_base"
    git diff --name-only --cached
    git ls-files --others --exclude-standard
  } | sort -u
)
[ -n "$changed" ] || { echo "test_affected: no changes — nothing to test" >&2; exit 0; }

# The enforcement scripts' door, ABOVE everything that can exec: the index check,
# the global-effect escalation and the source filter all end in a `full()` that
# excludes the goldens, so a gate edit reaching any of them first would run ZERO
# golden tests - which is the whole defect this closes (measured on the 2nd port,
# 2026-08-01: SRC_EXT_RE is a per-stack knob defaulting to `\.py$`, so shell fell
# out at "no source changes - nothing to test").
if [ -n "${HARNESS_SRC_RE:-}" ] && printf '%s\n' "$changed" | grep -Eq "$HARNESS_SRC_RE"; then
  run_goldens "harness source changed"
fi

[ -f "$INDEX_MARKER" ] || full "no code index ($INDEX_MARKER missing)"

# ponytail: global-effect files the index can't trace (fixtures, deps, schema) escalate to full
printf '%s\n' "$changed" | grep -Eq "$GLOBAL_EFFECT_RE" \
  && full "global-effect file changed"

changed_py=$(printf '%s\n' "$changed" | grep -E "$SRC_EXT_RE" || true)
[ -n "$changed_py" ] || { echo "test_affected: no source changes — nothing to test" >&2; exit 0; }

changed_tests=$(printf '%s\n' "$changed_py" | grep "^$TESTS_DIR/" || true)
changed_src=$(printf '%s\n' "$changed_py" | grep -v "^$TESTS_DIR/" || true)

# shared helpers under tests/ (non test_*.py) have dependents the index doesn't track
if [ -n "$changed_tests" ] && printf '%s\n' "$changed_tests" | grep -qvE "$TEST_FILE_RE"; then
  full "non-test .py under tests/ changed"
fi

affected=""
if [ -n "$changed_src" ]; then
  # a deleted source's reverse-dependents vanish from the index with it — only full is correct
  for f in $changed_src; do
    [ -f "$f" ] || full "source file deleted ($f)"
  done
  sh -c "$INDEX_SYNC_CMD" >/dev/null 2>&1 || full "index sync failed"
  affected=$(printf '%s\n' "$changed_src" | sh -c "$AFFECTED_TESTS_CMD" 2>/dev/null) \
    || full "affected-tests query failed"
  [ -n "$affected" ] || full "index found no affected tests for source changes"
fi

targets=$(
  printf '%s\n%s\n' "$changed_tests" "$affected" | grep -v '^$' | sort -u |
  while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done
)
[ -n "$targets" ] || full "no resolvable test targets"

echo "test_affected: running $(printf '%s\n' "$targets" | wc -l | tr -d ' ') affected test file(s)" >&2
sh "$script_dir/device_telemetry.sh" test-affected pass "selected" 2>/dev/null || :
# shellcheck disable=SC2086
exec $AFFECTED_RUNNER_CMD $targets
