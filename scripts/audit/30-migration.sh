#!/bin/sh
# Migration safety: destructive ops need an acknowledgment, history stays linear.
CHECK="migration"
. "$(dirname "$0")/lib.sh"

if [ "$mode" = "nonpipeline" ]; then _dev_rec n/a "nonpipeline-branch"; exit 0; fi

# migrations are per-repo (repo profile); no migrations dir = nothing to audit
if [ -z "${MIGRATIONS_DIR:-}" ]; then
  _dev_rec skip "profile-off"
  say "repo profile sets no MIGRATIONS_DIR - skipping (declared, not silent)"
  exit 0
fi

# --- destructive-migration acknowledgment: data-loss ops must be surfaced.
# Scope to upgrade() only - every migration's downgrade() legitimately drops.
# Case-insensitive + space/underscore so raw SQL (op.execute("DROP TABLE..")) counts.
# DELETE FROM / UPDATE ... SET are data-destructive too, not just DDL.
if [ -n "$base" ]; then
  destructive=0
  for mf in $(git diff --name-only "$base" HEAD -- "$MIGRATIONS_DIR/" 2>/dev/null | grep "\.py$"); do
    [ -f "$mf" ] || continue
    # Scan the WHOLE file EXCEPT the downgrade() body (every downgrade legitimately
    # drops). Old range /upgrade/,/downgrade/ missed helpers defined AFTER
    # downgrade() but called from upgrade(). Here: skip only lines inside a
    # def downgrade(...) block (until the next top-level def or dedent to col 0).
    n=$(awk '
      /^def downgrade/ {skip=1; next}
      /^def / && skip {skip=0}
      /^[^[:space:]#]/ && skip && !/^def / {skip=0}
      !skip {print}
    ' "$mf" | grep -icE "drop[[:space:]_](table|column|constraint|index)|alter[[:space:]_]column|truncate|delete[[:space:]]+from|update[[:space:]]+[^[:space:]]+[[:space:]]+set[[:space:]]" || true)
    destructive=$((destructive + ${n:-0}))
  done
  if [ "${destructive:-0}" -gt 0 ]; then
    if [ -n "$dlog" ] && grep -q "파괴적 변경" "$dlog"; then
      say "destructive migration ops acknowledged in decision log"
    else
      hard_violation "migration contains destructive ops (drop/alter/delete/update, $destructive lines) but decision log has no '파괴적 변경' acknowledgment - the gate briefing must state the data impact in plain language"
    fi
  fi
fi

# --- alembic history must stay linear (concurrent schema features serialize) ---
if ls "$MIGRATIONS_DIR"/versions/*.py >/dev/null 2>&1; then
  # grep -o handles merge migrations too: down_revision = ("a", "b") yields both ids
  all_revs=$(grep -h "^revision[[:space:]]*[:=]" "$MIGRATIONS_DIR"/versions/*.py 2>/dev/null | grep -oE "[\"'][A-Za-z0-9_]+[\"']" | tr -d "\"'")
  all_downs=$(grep -h "^down_revision[[:space:]]*[:=]" "$MIGRATIONS_DIR"/versions/*.py 2>/dev/null | grep -oE "[\"'][A-Za-z0-9_]+[\"']" | tr -d "\"'" || true)
  heads=0
  for r in $all_revs; do
    echo "$all_downs" | grep -qx "$r" || heads=$((heads + 1))
  done
  if [ "$heads" -gt 1 ]; then
    hard_violation "alembic history has $heads heads - migration graph diverged; serialize concurrent schema features (team-policy 동시 개발) and merge revisions"
  fi
fi

if [ "$fail" -eq 0 ]; then _dev_rec pass; say "ok"; fi
exit "$fail"
