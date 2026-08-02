#!/bin/sh
# Shared context for the process-audit checks (scripts/audit/NN-*.sh).
# Source this - it resolves branch/mode/base/gate and defines the violation
# helpers. A sourcing check exits 0 here when the audit does not apply.
#
# Env (set by CI): AUDIT_BRANCH (head branch), AUDIT_LABELS (space-separated PR labels)
set -u

branch="${AUDIT_BRANCH:-${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-$(git symbolic-ref --quiet --short HEAD || echo "")}}}"
branch="${branch#refs/heads/}"
labels="${AUDIT_LABELS:-}"

fail=0
say() { echo "process-audit[${CHECK:-audit}]: $*"; }
_dev_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)
_dev_rec() { [ -n "${_dev_dir:-}" ] || return 0; sh "$_dev_dir/device_telemetry.sh" "audit:${CHECK:-audit}" "$1" "${2:-}" 2>/dev/null || :; }
violation() {
  if [ "${exempt:-0}" = "1" ]; then
    _dev_rec fire "exempt: $*"
    say "WARN(exempt) - $*"
  else
    _dev_rec fire "$*"
    say "FAIL - $*"
    fail=1
  fi
}
# safety-core checks that audit-exempt can NOT downgrade: lock integrity,
# destructive migrations, gate bypass, migration-history divergence.
# (otherwise one label is worth the whole audit)
hard_violation() {
  _dev_rec fire "hard: $*"
  say "FAIL(hard - audit-exempt does not apply) - $*"
  fail=1
}

# audit-exempt downgrades process violations to warnings - never the safety core.
exempt=0
case " $labels " in
  *" audit-exempt "*)
    # announce once (in the first check), not once per check
    [ "${CHECK:-}" = "process-chain" ] && say "WARN - audit-exempt label present; process checks report as warnings, safety-core checks still fail (reason must be in the PR body)"
    exempt=1
    ;;
esac

case "$branch" in
  "") say "no branch name available - skipping (audit runs on PRs only)"; exit 0 ;;
  master | main) exit 0 ;;
  chore/* | docs/* | refactor/*) mode=nonpipeline ;;
  feat/*) mode=feat ;;
  fix/*) mode=fix ;;
  hotfix/*) mode=hotfix ;;
  *) say "WARN - unknown branch prefix '$branch'; auditing as feat"; mode=feat ;;
esac

ctx=".agents/context"

# --- repo profile (portability boundary): all repo-specific detection knobs
# live in $ctx/repo-profile.sh. FAIL CLOSED when absent or incomplete - without
# it, gate re-derivation silently matches nothing and the safety core becomes
# a no-op in a transplanted repo (the worst failure mode for a control system).
if [ -f "$ctx/repo-profile.sh" ]; then
  . "$ctx/repo-profile.sh"
else
  say "FAIL(hard - audit-exempt does not apply) - $ctx/repo-profile.sh missing; gate re-derivation cannot run without the repo profile (see .agents/PORTING.md)"
  exit 1
fi
for _v in SRC_DIR TESTS_DIR DEPS_MANIFEST API_GATE_RE HIGH_RISK_PATH_RE HIGH_RISK_CONTENT_RE; do
  eval "[ -n \"\${$_v:-}\" ]" || {
    say "FAIL(hard - audit-exempt does not apply) - repo-profile.sh does not set required variable $_v"
    exit 1
  }
done

# --- diff base + gate re-derivation (default branch resolved, never hardcoded) ---
audit_dir=$(dirname "$0")
default_ref=$(sh "$audit_dir/../default_branch.sh" 2>/dev/null || echo "")
if [ -n "$default_ref" ]; then
  git fetch -q origin "${default_ref#origin/}" 2>/dev/null || true
else
  git fetch -q origin master 2>/dev/null || true
  git fetch -q origin main 2>/dev/null || true
  default_ref=$(sh "$audit_dir/../default_branch.sh" 2>/dev/null || echo "")
fi
base=""
[ -n "$default_ref" ] && base=$(git merge-base "$default_ref" HEAD 2>/dev/null || echo "")
gate=""
changed=""
gate_unknown=0
if [ -n "$base" ]; then
  changed=$(git diff --name-only "$base" HEAD)
  [ -n "${MIGRATIONS_DIR:-}" ] && echo "$changed" | grep -q "^$MIGRATIONS_DIR/versions/" && gate="$gate DB(migration)"
  [ -n "${MODELS_DIR:-}" ] && echo "$changed" | grep -q "^$MODELS_DIR/" && gate="$gate DB(model)"
  git diff "$base" HEAD -- "$SRC_DIR/" 2>/dev/null | grep -qE "$API_GATE_RE" && gate="$gate API"
  echo "$changed" | grep -q "^$DEPS_MANIFEST\$" && gate="$gate deps"
  [ -n "${SETTINGS_RE:-}" ] && echo "$changed" | grep -qE "$SETTINGS_RE" && gate="$gate settings"
  # high-risk paths (risk-tiered gate): always gated, pre-approved patterns don't apply.
  echo "$changed" | grep -qE "$HIGH_RISK_PATH_RE" && gate="$gate high-risk"
  # high-risk CONTENT heuristic: payment/PII vocabulary in added lines. Coarse on
  # purpose - a hit only demands a human-gate record, not a redesign.
  git diff "$base" HEAD -- "$SRC_DIR/" 2>/dev/null | grep -qiE "$HIGH_RISK_CONTENT_RE" && gate="$gate high-risk(content)"
else
  gate_unknown=1
fi

# --- bootstrap: the PR that INSTALLS this harness ---------------------------
# Self-detected, not a branch-name convention (a prefix would be an opt-in bypass
# anyone could type). If the diff ADDS .agents/workflow.md, the pipeline itself is
# what is arriving, so the artifacts this audit normally demands cannot exist yet:
# there is no feature, hence no stage-4 tests to lock. Requiring them made the
# install PR unpassable under EVERY branch prefix (measured on the first real port,
# 2026-07-26: chore/* hard-failed on the deps+high-risk gate, feat/* on the missing
# lock marker - and audit-exempt cannot waive either).
#
# What still holds on a bootstrap PR: destructive-migration and supply-chain
# checks, and the enforcement scripts' own golden tests, which run in a sandbox
# (tests/harness/) and are the real proof that what is being installed
# works. Only the "did a pipeline run" evidence is waived.
bootstrap=0
if [ -n "$base" ] && git diff --name-status --diff-filter=A "$base" HEAD 2>/dev/null |
     grep -q "[[:space:]]\.agents/workflow\.md$"; then
  # flag only: lib.sh is sourced by EVERY check, so announcing or recording here
  # would emit one banner and one telemetry row per script and corrupt the hit
  # data. The script that actually waives something says so.
  bootstrap=1
fi

feature=$(echo "$branch" | cut -d/ -f2-)
feature_flat=$(echo "$branch" | tr '/' '-')

# --- resolve decision log + artifact dir (feature name = branch name per workflow.md) ---
dlog=""
for c in "$ctx/decisions/$feature.md" "$ctx/decisions/$feature_flat.md"; do
  [ -f "$c" ] && dlog="$c" && break
done
adir=""
for c in "$ctx/artifacts/$feature" "$ctx/artifacts/$feature_flat"; do
  [ -d "$c" ] && adir="$c" && break
done
