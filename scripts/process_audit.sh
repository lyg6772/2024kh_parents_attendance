#!/bin/sh
# Process-conformance audit (CI, PR boundary) - orchestrates the checks in
# scripts/audit/, split by concern:
#   10-process-chain   artifact chain, verdict evidence, gate re-derivation
#   20-test-lock       server-side test-LOCK backstop (lock window audit)
#   30-migration       destructive ops + alembic head linearity
#   40-supply-chain    PyPI slopsquatting guard (the only networked check)
# Shared context (branch/mode/base/gate) lives in scripts/audit/lib.sh.
#
# Env (set by CI): AUDIT_BRANCH (head branch), AUDIT_LABELS (space-separated PR labels)
set -u

dir="$(dirname "$0")/audit"
rc=0
for c in "$dir"/[0-9]*-*.sh; do
  [ -f "$c" ] || continue  # unmatched glob passes the literal pattern in POSIX sh
  echo "== $(basename "$c" .sh) =="
  sh "$c" || rc=1
done

if [ "$rc" -eq 0 ]; then
  echo "process-audit: PASS - pipeline conformance verified"
else
  echo "process-audit: FAIL - see the failing check above. 'audit-exempt' label + reason in the PR body downgrades PROCESS checks to warnings; safety-core checks (lock window, destructive migration, gate bypass, alembic heads) always fail"
fi
exit "$rc"
