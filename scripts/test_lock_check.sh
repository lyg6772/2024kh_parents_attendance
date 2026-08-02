#!/bin/sh
# pre-commit `test-lock` hook body: blocks commits touching tests/ while a
# matching pipeline test-LOCK marker exists (stage 4-7). Commit-time twin of
# scripts/test_lock_guard.sh (edit-time, Claude Code PreToolUse) - same
# branch-match rules. Extracted from inline YAML so it is testable and the
# matching logic lives in one greppable place per trigger point.
set -u

# pre-resolve like the sibling scripts: a relative $0 must not depend on cwd
_dev_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)

# Scope to the contract this hook governs: only a commit that actually STAGES
# files under TESTS_DIR can alter the locked test contract.
#
# Without this the check blocks EVERY commit while a lock exists. Two real
# consequences, both of which train people toward habitual TEST_LOCK_OVERRIDE
# (which defeats the control entirely):
#   - raw-hook installs (no pre-commit framework, so no `files: ^tests/`
#     scoping) block the pipeline's OWN stage-5 implementation commits
#   - on detached HEAD the fail-closed branch below fires for rebase,
#     cherry-pick --continue and bisect commits that touch no tests at all
# Server-side lock-window auditing (audit/20-test-lock.sh) is unchanged, so the
# backstop still sees any test edit inside the window.
#
# An empty staged list is NOT proof this is a non-commit: `git commit --amend`
# with nothing newly staged, and rebase amends, also produce one. So it falls
# through to the lock check (fail-closed) rather than being treated as "no
# commit, nothing to guard" - manual runs and gate demos land here too.
_top=$(git rev-parse --show-toplevel 2>/dev/null || echo .)
# Sourced in a SUBSHELL with its OUTPUT DISCARDED: the profile is repo-controlled
# and this is a safety check. Variables it defines must not reach the logic below
# (b/any/hit), and anything it prints must not end up concatenated into the value
# - either would make the prefix match nothing and exit 0, disabling the lock.
_tests_dir=$(
  { [ -f "$_top/.agents/context/repo-profile.sh" ] &&
      . "$_top/.agents/context/repo-profile.sh"; } >/dev/null 2>&1
  printf '%s' "${TESTS_DIR:-tests}"
)
# the subshell inherits `set -u`: a profile referencing an unbound variable kills
# it before printf, and an empty value would make the prefix "/" match nothing -
# exit 0, i.e. the lock silently disabled. Fall back instead.
[ -n "$_tests_dir" ] || _tests_dir=tests
_tests_dir=${_tests_dir#./}          # './tests' must behave like 'tests'
_tests_dir=${_tests_dir%/}          # 'tests/'   must behave like 'tests'
# core.quotePath=false: git otherwise C-quotes non-ASCII paths
# ("tests/test_\355...py"), which would not match the prefix below and would
# silently exit 0 — the fail-open this scoping must never introduce.
# --no-renames: with rename detection on (the default), `git mv tests/test_x.py
# elsewhere.py` stages only the DESTINATION, so the tests/ prefix disappears and
# the lock is bypassed. --no-renames splits it back into delete+add.
_staged=$(git -c core.quotePath=false diff --cached --no-renames --name-only 2>/dev/null || echo "")
if [ -n "$_staged" ]; then
  # LITERAL path-prefix match, never a regex: interpolating TESTS_DIR into a
  # pattern means a trailing slash or a metachar silently matches nothing, and
  # this safety control would exit 0 - failing OPEN, which is the one outcome a
  # lock guard must never have.
  _relevant=0
  _oldifs=$IFS
  IFS='
'
  set -f            # $_staged is unquoted below; a path with * must not glob
  for _f in $_staged; do
    case "$_f" in "$_tests_dir"/*) _relevant=1; break ;; esac
  done
  set +f
  IFS=$_oldifs
  [ "$_relevant" -eq 1 ] || exit 0
fi

b=$(git symbolic-ref --quiet --short HEAD || echo "")
any="" hit=""
for l in .agents/context/locks/*.lock; do
  [ -f "$l" ] || continue
  any="$l"
  l1=$(head -n 1 "$l")
  if [ -n "$b" ] && { [ "$l1" = "$b" ] || [ "$l1" = "${b#*/}" ]; }; then hit="$l"; fi
done
# detached HEAD: branch unknown -> fail closed while any lock exists
[ -z "$b" ] && [ -n "$any" ] && hit="$any"

# A matched lock that an override let through is still a DETECTION - recording
# it as "pass / lock-not-mine" would lie about both fields, and a device whose
# only real hits were overridden would read as "never fired".
if [ -n "$hit" ] && [ "${TEST_LOCK_OVERRIDE:-0}" = "1" ]; then
  sh "${_dev_dir:-.}/device_telemetry.sh" test-lock-check fire "env-override: $hit" 2>/dev/null || :
  exit 0
fi
if [ -n "$hit" ]; then   # the override case already returned above
  echo "tests/ is LOCKED (pipeline stage 4-7)"
  echo "$hit"
  [ -z "$b" ] && echo "detached HEAD - branch unknown, failing closed while locks exist"
  echo "human-approved fix -> TEST_LOCK_OVERRIDE=1 git commit (record approval in decision log)"
  sh "${_dev_dir:-.}/device_telemetry.sh" test-lock-check fire "$hit" 2>/dev/null || :
  exit 1
fi
# `pass` only when a lock actually existed and was evaluated - same rule as
# test_lock_guard.sh, so the twins' counts stay comparable.
[ -n "$any" ] && { sh "${_dev_dir:-.}/device_telemetry.sh" test-lock-check pass "lock-not-mine" 2>/dev/null || :; }
exit 0
