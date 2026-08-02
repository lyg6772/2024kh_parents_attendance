#!/bin/sh
# Device-hit telemetry: which enforcement devices actually FIRE in real use.
#
# PORTING.md §4 asks for this ("적중 0인 장치는 강등 후보") but there was no
# instrument, so the first real port could only report device hits by hand.
# Without counts there is no evidence for demoting a device that never fires or
# for hardening one that fires constantly.
#
#   sh scripts/device_telemetry.sh <device> <outcome> [detail]
#     fire        it detected a violation (normally a block; an audit-exempt
#                 label can downgrade the same detection to a warning)
#     pass        it ran and allowed
#     n/a         it evaluated and correctly did nothing (not applicable to this
#                 input: a docs-only diff, a push to a non-default ref)
#     skip        it never evaluated: a profile knob turned it off, or a human
#                 bypassed it BEFORE it could look (PR_REVIEW_SKIP). A human
#                 override AFTER a detection is `fire` - the detection happened
#     degraded    it ran, but not at full strength: an optimisation did not apply
#                 (the affected-test selector falling back to the full suite), or
#                 the guarantee itself was relaxed to avoid wedging the session
#                 (stop-validate letting a still-red turn through after its retry)
#     unavailable it could not run (tool missing) - NOT the same as pass
#
# Report-only. It MUST NEVER change a gate's outcome, so every failure path
# exits 0 - the exact opposite of the fail-closed gates it observes.
set -u
[ "$#" -ge 2 ] || exit 0

top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -n "$top" ] || exit 0
dir="$top/.agents/context/telemetry"
mkdir -p "$dir" 2>/dev/null || exit 0

# JSON-escape: backslash and quote, and strip control chars that would break the
# one-object-per-line contract.
esc() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\000-\037'
}

branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo "detached")

# the 2>/dev/null must wrap the REDIRECTION, not just printf: a failing `>>`
# is reported by the shell itself, and a hook that prints an error on every
# tool call is noise the user sees.
{
  printf '{"ts":"%s","device":"%s","outcome":"%s","branch":"%s","detail":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)" \
    "$(esc "$1")" "$(esc "$2")" "$(esc "$branch")" "$(esc "${3:-}")" \
    >>"$dir/devices.jsonl"
} 2>/dev/null || exit 0
exit 0
