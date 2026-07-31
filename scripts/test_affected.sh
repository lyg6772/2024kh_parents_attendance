#!/bin/sh
# Inner-loop accelerator: run only the tests affected by current changes,
# resolved through a code-index tool. The pre-push hook runs this selector;
# CI is the authority that always runs the full suite. Fail-closed: every
# uncertain path (no index, sync failure, query miss, global-effect file
# changed) falls back to the FULL suite, so it is faster but never weaker.
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
#   FULL_SUITE_CMD      full-suite runner (default pytest, harness dir excluded)
#   AFFECTED_RUNNER_CMD runner for the selected test files (default pytest)
set -u

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$(git rev-parse --show-toplevel)" || exit 1

[ -f .agents/context/repo-profile.sh ] && . .agents/context/repo-profile.sh
INDEX_MARKER=${INDEX_MARKER:-.codegraph/codegraph.db}
INDEX_SYNC_CMD=${INDEX_SYNC_CMD:-"codegraph sync -q"}
TESTS_DIR=${TESTS_DIR:-tests}
SRC_EXT_RE=${SRC_EXT_RE:-'\.py$'}
TEST_FILE_RE=${TEST_FILE_RE:-'(^|/)test_[^/]+\.py$'}
GLOBAL_EFFECT_RE=${GLOBAL_EFFECT_RE:-'(^|/)conftest\.py$|^pyproject\.toml$|^uv\.lock$|^alembic\.ini$|^migrations/'}
FULL_SUITE_CMD=${FULL_SUITE_CMD:-"pytest -q --ignore=$TESTS_DIR/harness"}
AFFECTED_RUNNER_CMD=${AFFECTED_RUNNER_CMD:-"pytest -q"}
AFFECTED_TESTS_CMD=${AFFECTED_TESTS_CMD:-"codegraph affected --stdin -q -f '$TESTS_DIR/test_*.py'"}

# harness golden tests stay CI-only (same exclusion as the old pre-push hook)
full() {
  sh "$script_dir/device_telemetry.sh" test-affected degraded "fallback-full: $1" 2>/dev/null || :
  echo "test_affected: $1 — running full suite" >&2
  # shellcheck disable=SC2086
  exec $FULL_SUITE_CMD
}

[ -f "$INDEX_MARKER" ] || full "no code index ($INDEX_MARKER missing)"

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
