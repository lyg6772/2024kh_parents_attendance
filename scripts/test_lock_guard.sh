#!/bin/sh
# Claude Code PreToolUse guard: blocks agent edits to tests/ while a matching
# pipeline test-LOCK marker exists (stage 4-7). Edit-time twin of the
# pre-commit `test-lock` hook - same branch-match rules, earlier trigger.
#
# KNOWN LIMIT: the paths below are hardcoded to `tests/`, while the commit-time
# twin honors TESTS_DIR from repo-profile.sh. In a repo whose tests live
# elsewhere this edit-time layer is inert; the commit-time hook and the CI
# lock-window audit are the enforcement there. Interpolating TESTS_DIR here
# means threading it through the embedded python patterns too - not done yet.
set -u

# invoked as a hook with JSON on a pipe; a human running it in a terminal would
# otherwise hang on cat waiting for stdin. No tty = real hook input.
[ -t 0 ] && exit 0

# resolve BEFORE any cd and before the first telemetry call below: a relative
# $0 would not survive the cd, and the record would land nowhere.
_dev_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)

input=$(cat 2>/dev/null || echo "")
# Edit/Write/NotebookEdit expose the target directly (file_path/notebook_path).
# Bash hides it inside a command string - detect only WRITES into tests/
# (redirects, tee, sed -i, cp/mv dest, python open(w/a)); read-only refs like
# `pytest tests/` or `cat tests/x` must pass. This is best-effort by design -
# the pre-commit test-lock hook (path-based, tool-agnostic) is the real backstop,
# so a parse miss fails OPEN here rather than blocking every Bash call.
path=$(printf '%s' "$input" | python3 -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit(0)
ti = d.get("tool_input", {})
fp = ti.get("file_path") or ti.get("notebook_path")
if fp:
    print(fp); raise SystemExit(0)
cmd = ti.get("command") or ""
patterns = [
    r">>?\s*[\x27\"]?(?:\./)?tests/",
    r"\btee\b[^|;&]*\btests/",
    r"\bsed\b[^|;&]*-i[^|;&]*\btests/",
    r"\b(?:cp|mv|install)\b[^|;&]*\stests/\S",
    r"open\([^)]*tests/[^)]*[\x27\"][wa]",
    r"\b(?:truncate|dd)\b[^|;&]*\btests/",
]
print("tests/__BASH_WRITE__" if any(re.search(p, cmd) for p in patterns) else "")
' 2>/dev/null) || {
  # `|| exit 0` here also covers python3 being ABSENT, not just a parse miss:
  # in that case the guard no-ops for Edit/Write too, since $path comes from the
  # same call. Fail-open is still the right call for an edit-time best-effort
  # layer (blocking every tool call on a machine without python3 is worse), but
  # it must not be silent - the commit-time hook and the CI lock-window audit
  # remain the real backstops.
  command -v python3 >/dev/null 2>&1 || {
    sh "${_dev_dir:-.}/device_telemetry.sh" test-lock-guard unavailable "no-python3" 2>/dev/null || :
    echo "test_lock_guard: python3 unavailable - edit-time LOCK guard is INACTIVE (commit-time hook still enforces)" >&2
  }
  exit 0
}
[ -z "$path" ] && exit 0

root=${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo "")}
[ -z "$root" ] && exit 0
case "$path" in
  "$root"/tests/* | tests/*) ;;
  *) exit 0 ;;
esac

cd "$root" || exit 0
b=$(git symbolic-ref --quiet --short HEAD || echo "")
any="" hit=""
for l in .agents/context/locks/*.lock; do
  [ -f "$l" ] || continue
  any="$l"
  l1=$(head -n 1 "$l")
  if [ -n "$b" ] && { [ "$l1" = "$b" ] || [ "$l1" = "${b#*/}" ]; }; then hit="$l"; fi
done
[ -z "$b" ] && [ -n "$any" ] && hit="$any"
# `pass` only where the guard ACTUALLY evaluated a lock and allowed the edit -
# not on the trivial early exits (non-tests path, no lock at all), which fire on
# every tool call and would drown the table.
if [ -z "$hit" ]; then
  [ -n "$any" ] && { sh "${_dev_dir:-.}/device_telemetry.sh" test-lock-guard pass "other-branch-lock" 2>/dev/null || :; }
  exit 0
fi
# human-created unblock marker (touch <lock>.override) - commit still needs
# TEST_LOCK_OVERRIDE=1, and the CI lock-window audit sees it either way.
if [ -f "$hit.override" ]; then
  sh "${_dev_dir:-.}/device_telemetry.sh" test-lock-guard fire "human-override-marker" 2>/dev/null || :
  exit 0
fi

{
  echo "BLOCKED: tests/ is LOCKED (pipeline stage 4-7): $hit"
  [ -z "$b" ] && echo "detached HEAD - branch unknown, failing closed while locks exist"
  echo "Tests are a contract - do not edit them to make the implementation pass."
  echo "If a test is objectively wrong: report to the human. After approval, the"
  echo "HUMAN runs: sh scripts/unlock_tests.sh <feature>  (tty-confirmed, unblocks"
  echo "editing), then the fix is committed with TEST_LOCK_OVERRIDE=1 and the"
  echo "approval is recorded in the decision log as a SAME-LINE entry:"
  echo "  override 사용: <무엇을, 왜>   (the audit accepts no other form)"
  echo "Stage 7 PASS deletes the lock and any .override marker."
} >&2
sh "${_dev_dir:-.}/device_telemetry.sh" test-lock-guard fire "$path" 2>/dev/null || :
exit 2
