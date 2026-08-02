#!/bin/sh
# Human-anchored test-LOCK override: creates <lock>.override only after a human
# types UNLOCK on /dev/tty. Agent shells have no controlling terminal, so an
# agent cannot take this path on its own (same anchor as pr_review_gate.sh SKIP).
#
# A raw `touch <lock>.override` still works mechanically - this script is the
# SANCTIONED path; the CI lock-window audit + 'override 사용:' telemetry are the
# backstop that surfaces unsanctioned overrides on the PR.
set -u

feature="${1:-}"
if [ -z "$feature" ]; then
  echo "usage: sh scripts/unlock_tests.sh <feature-name>"
  exit 2
fi
lock=".agents/context/locks/$feature.lock"
if [ ! -f "$lock" ]; then
  echo "unlock-tests: no lock marker at $lock"
  exit 1
fi

if printf 'unlock-tests: re-opens LOCKED tests for %s - type UNLOCK to confirm (human only): ' "$feature" >/dev/tty 2>/dev/null &&
  IFS= read -r ans </dev/tty 2>/dev/null && [ "$ans" = "UNLOCK" ]; then
  : >"$lock.override"
  echo "unlock-tests: $lock.override created"
  echo "unlock-tests: commit the approved test fix with TEST_LOCK_OVERRIDE=1 and record 'override 사용:' in the decision log"
  exit 0
fi
echo "unlock-tests: requires a human typing UNLOCK on the terminal (/dev/tty) - refusing"
exit 1
