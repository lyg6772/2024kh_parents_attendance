#!/bin/sh
# Does the open PR's body actually use the repo's PR template?
#
# `gh pr create --body` silently IGNORES .github/PULL_REQUEST_TEMPLATE.md - the
# template only auto-inserts in the web UI. ship-pr/SKILL.md has named this an
# anti-pattern from the start, and it was still violated on five consecutive PRs
# in one session, because the rule lived only in prose. A rule with no device is
# a suggestion; this is the device.
#
#   sh scripts/pr_body_check.sh [pr-number]
#
# SCOPE: on the FIRST push of a branch no PR exists yet, so this exits 0 - it
# cannot catch a free-form body at creation time. ship-pr runs it right after
# `gh pr create` for that; the pre-push hook is the backstop that catches a body
# left free-form or gone stale on any later push.
#
# No template in the repo, no gh, no PR yet -> nothing to enforce, exit 0. It
# fails ONLY on the case it exists for: a template is present and the body
# ignores it.
set -u

top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
tpl="$top/.github/PULL_REQUEST_TEMPLATE.md"
[ -f "$tpl" ] || exit 0
command -v gh >/dev/null 2>&1 || {
  echo "pr-body-check: gh not available - skipping (template compliance unverified)" >&2
  exit 0
}

# A failed gh call exits 0 above (unverifiable). An EMPTY body does NOT - it is
# 100% of the template absent, the most degenerate case of what this catches, and
# it used to pass. Left empty, the loop below counts every heading as missing.
err=$(mktemp) || exit 0
trap 'rm -f "$err"' EXIT INT TERM
if ! body=$(gh pr view ${1:+"$1"} --json body 2>"$err" -q .body); then
  # "no PR yet" is the normal first-push case and stays quiet. Anything else -
  # auth expired, network down - is UNAVAILABLE, not a pass, and must say so or a
  # broken gh reads like a clean push forever.
  case "$(cat "$err" 2>/dev/null)" in
    *"no pull requests found"*|*"no open pull requests"*) ;;
    *) echo "pr-body-check: gh call failed - template compliance UNVERIFIED" >&2 ;;
  esac
  exit 0
fi

# The template's section headings are its contract. Require most of them rather
# than all: the template itself says unused sections may be deleted.
missing=0 total=0 absent=""
tmp=$(mktemp) || exit 0
trap 'rm -f "$tmp" "$err"' EXIT INT TERM
grep '^## ' "$tpl" > "$tmp" 2>/dev/null || true

while IFS= read -r heading; do
  [ -n "$heading" ] || continue
  total=$((total + 1))
  case "$body" in
    *"$heading"*) ;;
    *) missing=$((missing + 1)); absent="$absent
    $heading" ;;
  esac
done < "$tmp"

[ "$total" -gt 0 ] || exit 0

# more than half the headings absent = the body was written free-form
if [ $((missing * 2)) -gt "$total" ]; then
  echo "pr-body-check: this PR's body ignores .github/PULL_REQUEST_TEMPLATE.md" >&2
  echo "  $missing of $total template sections are absent:$absent" >&2
  echo "  \`gh pr create --body\` does NOT apply the template - fill it in and" >&2
  echo "  \`gh pr edit --body-file\` the result (ship-pr/SKILL.md)." >&2
  exit 1
fi

echo "pr-body-check: body follows the template ($((total - missing))/$total sections present)"
exit 0
