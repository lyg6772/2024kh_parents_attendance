#!/bin/sh
# Blocks a direct `git push` to the remote default branch (pre-push stage) —
# the local stand-in for GitHub branch protection, which is unavailable on this
# plan (team-policy § 위험 수용 기록). Policy is PR-only, even for hotfixes.
#
# A human can pass once by typing PUSH on /dev/tty; agent shells have no
# controlling terminal, so an agent cannot take this path on its own
# (same anchor as pr_review_gate.sh SKIP / unlock_tests.sh UNLOCK).
set -u

# pre-resolve like the sibling scripts, so the pattern holds if a cd is ever added
_dev_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)

# CI mirrors the pre-push stage with `pre-commit run` — no push happens there.
if [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; then
  sh "${_dev_dir:-.}/device_telemetry.sh" protect-default-branch n/a "ci" 2>/dev/null || :
  exit 0
fi

# Set by pre-commit only during a real `git push` (e.g. refs/heads/master).
# Absent = the stage was run manually; nothing is being pushed.
remote_ref="${PRE_COMMIT_REMOTE_BRANCH:-}"
[ -z "$remote_ref" ] && exit 0

default_ref=$(sh "$(dirname "$0")/default_branch.sh") || {
  sh "${_dev_dir:-.}/device_telemetry.sh" protect-default-branch unavailable "no-default-ref" 2>/dev/null || :
  echo "protect-default-branch: cannot resolve default branch - failing closed"
  exit 1
}
default_name=${default_ref#origin/}

case "$remote_ref" in
  "refs/heads/$default_name") ;;
  *) sh "${_dev_dir:-.}/device_telemetry.sh" protect-default-branch n/a "non-default-ref" 2>/dev/null || :
     exit 0 ;;
esac

echo "protect-default-branch: direct push to '$default_name' - policy is PR-only (team-policy 브랜치 전략)."
if printf 'type PUSH to confirm the direct push (human only): ' 2>/dev/null >/dev/tty &&
  IFS= read -r ans </dev/tty 2>/dev/null && [ "$ans" = "PUSH" ]; then
  echo "protect-default-branch: confirmed by human - record 'override 사용:' in the decision log"
  sh "${_dev_dir:-.}/device_telemetry.sh" protect-default-branch fire "human-override" 2>/dev/null || :
  exit 0
fi
echo "protect-default-branch: refusing direct push to '$default_name' (no human confirmation on /dev/tty)"
sh "${_dev_dir:-.}/device_telemetry.sh" protect-default-branch fire "$default_name" 2>/dev/null || :
exit 1
