#!/bin/sh
# Test-LOCK backstop (server-side; local hooks are bypassable).
CHECK="test-lock"
. "$(dirname "$0")/lib.sh"

if [ "$mode" = "nonpipeline" ]; then _dev_rec n/a "nonpipeline-branch"; exit 0; fi
# no feature => no stage-4 tests => nothing to lock. Waived, not skipped silently.
if [ "${bootstrap:-0}" = "1" ]; then
  say "bootstrap PR - no feature, so no stage-4 tests to lock; marker not required"
  _dev_rec n/a "bootstrap"
  exit 0
fi

# Does the decision log carry a REAL override record?
# Rationale and the exact accepted form live in override_recorded() below.
override_recorded() {
  # ONE contract: the `override 사용: <무엇을, 왜>` line the kernel already
  # mandates (QUICKSTART, team-policy). A bare "TEST_LOCK_OVERRIDE" grep used to
  # short-circuit this, but a log that merely documents the procedure
  # ("TEST_LOCK_OVERRIDE=1 git commit") contains the token too - same
  # token-presence defect this function exists to remove.
  # Require the SAME-LINE colon form that QUICKSTART/team-policy specify
  # ('override 사용: <무엇을, 왜>'). A heading followed by a lookahead was tried
  # and removed: it accepted whatever non-empty line came next, so an unrelated
  # bullet ('- 다음 단계: 배포') counted as an approval record - fail-open in a
  # safety-core check. Under-accepting here is merely annoying; over-accepting
  # silently licenses weakening a locked test.
  awk '
    $0 ~ /[Oo]verride[[:space:]]*사용[[:space:]]*:/ {
      v = $0
      sub(/.*[Oo]verride[[:space:]]*사용[[:space:]]*:[[:space:]]*/, "", v)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
      sub(/^([-*+][[:space:]]*|•[[:space:]]*)/, "", v)
      if (!placeholder(v)) found = 1
    }
    function placeholder(s) {
      # also reject the fill-in forms used in the docs: "<무엇을, 왜>", "(무엇을, 왜)"
      if (s ~ /^[<(].*[>)]$/) return 1
      return (s ~ /^(없음|없다|없습니다|해당[[:space:]]*없음|[Nn]one|[Nn]\/?[Aa]|(-)+|(—)+)?\.?$/)
    }
    END { exit(found ? 0 : 1) }
  ' "$1"
}

# 1) an active lock marker at PR time means stage 7 never passed
for c in "$ctx/locks/$feature.lock" "$ctx/locks/$feature_flat.lock"; do
  if [ -f "$c" ]; then
    hard_violation "test-LOCK marker still present ($c) - stage 7 has not passed; delete it only via stage-7 PASS"
  fi
done

# without a merge-base the window audit cannot run; 10-process-chain already
# fails the whole audit closed in that case.
if [ -n "$base" ]; then
  # 2) lock-window audit: $TESTS_DIR/ edits between lock creation and lock deletion
  #    require an override record (human-approved stage-4 fix)
  #    --full-history is REQUIRED: on a PR the CI checks out refs/pull/N/merge (a
  #    merge commit). A conformant feature adds the lock at stage 4 and DELETES it
  #    at stage 7, so the merge commit is TREESAME to the default branch for the
  #    lock path and default history simplification prunes the whole feature side
  #    -> lock_add comes back empty and every passing feature false-fails "never locked".
  lock_add=$(git log --full-history --diff-filter=A --format=%H "$base"..HEAD -- "$ctx/locks/$feature.lock" "$ctx/locks/$feature_flat.lock" 2>/dev/null | tail -1)
  # a feature that ran the pipeline must have created a lock at stage 4 -
  # its absence from history means the pipeline (or a history rewrite) skipped it.
  # HARD: never-locking is the cheapest way to have no lock window at all, and
  # the lock window is safety core (team-policy) - audit-exempt must not waive it.
  if [ "$mode" = "feat" ] && [ -z "$lock_add" ]; then
    hard_violation "no test-LOCK marker was ever committed on this branch - stage 4 never locked (or history was rewritten to hide the window)"
  fi
  # fix/hotfix that touch tests/ must also lock them (tests are the spec there too)
  if [ "$mode" != "feat" ] && [ -z "$lock_add" ] && echo "$changed" | grep -q "^$TESTS_DIR/"; then
    hard_violation "$mode branch modifies tests/ but never committed a test-LOCK marker - the repro test must be locked before the fix (team-policy)"
  fi
  if [ -n "$lock_add" ]; then
    # scan lock creation .. HEAD (NOT lock deletion): tests edited AFTER stage-7
    # unlocked them, in a later commit on the same PR, must still show an
    # override record - otherwise the approved test contract is silently altered
    # post-review (TOCTOU: lock, pass, then weaken the test).
    # Exclude the upstream branch: if the dev merges the default branch in to
    # resolve conflicts, its own tests/ history becomes reachable from HEAD and
    # would false-fire this check - those edits belong upstream, not to this branch.
    excl=""
    for ref in $default_ref origin/master origin/main; do
      git rev-parse --verify -q "$ref" >/dev/null 2>&1 && excl="$excl ^$ref"
    done
    locked_test_edits=$(git log --full-history --format="" --name-only "$lock_add"..HEAD $excl -- "$TESTS_DIR/" 2>/dev/null | grep -v '^$' | sort -u || true)
    if [ -n "$locked_test_edits" ]; then
      if [ -n "$dlog" ] && override_recorded "$dlog"; then
        # a recorded override is still a DETECTION - same rule as
        # test_lock_check.sh and the recorder header
        _dev_rec fire "override-record: $(echo "$locked_test_edits" | tr '\n' ' ')"
        say "tests/ edited in/after the LOCK window - override record found"
      else
        hard_violation "tests/ modified in/after the LOCK window without an 'override 사용:' record in the decision log: $(echo "$locked_test_edits" | tr '\n' ' ')"
      fi
    fi
  fi
fi

if [ "$fail" -eq 0 ]; then _dev_rec pass; say "ok"; fi
exit "$fail"
