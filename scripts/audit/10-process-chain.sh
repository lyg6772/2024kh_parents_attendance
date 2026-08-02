#!/bin/sh
# Process/format audit: the pipeline actually ran. Artifact chain exists,
# review verdict is real, and the design-gate classification is re-derived
# from the diff instead of trusting the agent's self-assessment.
CHECK="process-chain"
. "$(dirname "$0")/lib.sh"

# The refactor shadow device says it "promotes to a violation after hit data".
# Give it its own device name so that hit data actually exists.
_dev_rec_shadow() { [ -n "${_dev_dir:-}" ] || return 0; sh "$_dev_dir/device_telemetry.sh" "audit:refactor-shadow" fire "$*" 2>/dev/null || :; }

# --- non-pipeline branches (chore/docs/refactor): the ONLY audit is that they
# stay non-pipeline. A gate-triggering diff on these prefixes is the bypass route.
if [ "${bootstrap:-0}" = "1" ]; then
  # the installing PR changes deps and often brushes a high-risk path (its own
  # lint fix did, on the first real port); those gates exist to force a design
  # record for FEATURE work, which this is not.
  say "bootstrap PR (adds .agents/workflow.md) - pipeline-artifact checks waived; the sandbox goldens are the proof that what is being installed works"
  _dev_rec n/a "bootstrap"   # waived, not passed
  exit 0
fi

if [ "$mode" = "nonpipeline" ]; then
  if [ "$gate_unknown" = "1" ]; then
    hard_violation "branch '$branch' is outside the pipeline but gate conditions could not be re-derived (no merge-base) - fail closed; fetch full history or use a feat/ branch"
  elif [ -n "$gate" ]; then
    hard_violation "branch '$branch' is outside the pipeline but its diff triggers gate conditions ($gate) - use a feat/ branch and run the pipeline"
  else
    say "branch type '$branch' is outside the feature pipeline and its diff stays non-gate - ok"
  fi
  # refactor/* touching shared code should carry fix-grade verification (06+07
  # artifacts + decision log - team-policy 리팩토링 정책). NEW DEVICE in shadow
  # mode per 하네스 개선 루프 #2: warn-only until hit data justifies promotion.
  case "$branch" in
    refactor/*)
      _shadow_clean=1
      # boundary rule (team-policy 리팩토링 정책): refactoring = existing tests
      # stay green UNEDITED. A refactor branch touching tests contradicts the
      # branch type's definition - shadow warn (legit import-renames exist, so
      # not a hard red until hit data says otherwise).
      if [ -n "$base" ] && printf '%s\n' "$changed" | grep -q "^$TESTS_DIR/"; then
        _shadow_clean=0; _dev_rec_shadow "tests-edited"; say "WARN(shadow) - refactor branch modifies $TESTS_DIR/ - refactoring keeps existing tests green UNEDITED (team-policy 경계); if tests must change, this is a behavior change -> feat/fix pipeline"
      fi
      if [ -n "$base" ] && [ -n "${SHARED_CODE_RE:-}" ] && printf '%s\n' "$changed" | grep -qE "$SHARED_CODE_RE"; then
        missing=""
        if [ -n "$adir" ]; then
          ls "$adir"/06-*.md >/dev/null 2>&1 || missing="$missing 06-artifact"
          ls "$adir"/07-*.md >/dev/null 2>&1 || missing="$missing 07-artifact"
        else
          missing="$missing 06-artifact 07-artifact"
        fi
        [ -n "$dlog" ] || missing="$missing decision-log"
        if [ -n "$missing" ]; then
          _shadow_clean=0; _dev_rec_shadow "missing:$missing"; say "WARN(shadow) - refactor branch touches shared code without fix-grade verification (missing:$missing) - team-policy 리팩토링 정책; shadow device, promotes to a violation after hit data"
        fi
      fi
      [ "${_shadow_clean:-1}" -eq 1 ] && [ -n "${_dev_dir:-}" ] &&
        { sh "$_dev_dir/device_telemetry.sh" "audit:refactor-shadow" pass "clean" 2>/dev/null || :; }
      ;;
  esac
  # this arm DOES evaluate (it re-derives the gate conditions), so a clean run
  # is a pass, not "not applicable" - 20/30/40 exit immediately and use n/a
  if [ "$fail" -eq 0 ]; then _dev_rec pass "nonpipeline-branch"; fi
  exit "$fail"
fi

# pipeline branches fail closed too: without a merge-base the destructive,
# lock-window, gate and supply-chain checks cannot run - that must be a red,
# not a warning (shallow checkouts in derived projects would otherwise skip
# the entire safety core silently)
if [ "$gate_unknown" = "1" ]; then
  hard_violation "no merge-base with the default branch - safety-core checks cannot run; fail closed (use fetch-depth: 0 in CI)"
fi

# Does a named section carry actual CONTENT, not just its heading/phrase?
#
# Token-presence greps are why several gates were bypassable: writing the
# required words satisfied the check while the section stayed empty. Same class
# as 20-test-lock.sh's `override 사용` grep. Counts non-blank lines after the
# LAST occurrence of the phrase, stopping at the next heading; text on the
# phrase line itself beyond the phrase also counts.
section_has_body() { # section_has_body <file> <phrase>
  awk -v phrase="$2" '
    # Prefer a HEADING occurrence: once one is seen, a later prose mention must
    # not reset the anchor and blank out a section that really has content.
    {
      i = index($0, phrase)
      if (i > 0 && (!heading_seen || $0 ~ /^#+[[:space:]]/)) {
        if ($0 ~ /^#+[[:space:]]/) heading_seen = 1
        found = 1; stop = 0; body = 0
        depth = 0
        if (match($0, /^#+/)) depth = RLENGTH
        tail = substr($0, i + length(phrase))
        gsub(/[[:space:]:#*_-]/, "", tail)
        next
      }
    }
    # stop only at a heading of EQUAL-OR-SHALLOWER depth: a deeper subheading
    # (### under ##) is part of this section, not the end of it
    found && !stop && /^#+[[:space:]]/ {
      match($0, /^#+/)
      if (depth == 0 || RLENGTH <= depth) stop = 1
    }
    found && !stop && /[^[:space:]]/   { body++ }
    END { exit (found && (body > 0 || length(tail) > 0)) ? 0 : 1 }
  ' "$1" 2>/dev/null
}

[ -z "$dlog" ] && violation "decision log missing: $ctx/decisions/$feature.md"

require_artifact() {
  n="$1"
  if [ -z "$adir" ] || ! ls "$adir"/"$n"-*.md >/dev/null 2>&1; then
    violation "stage $n artifact missing under $ctx/artifacts/$feature/"
  fi
}

case "$mode" in
  feat) for n in 01 02 03 04 06 07; do require_artifact "$n"; done ;;
  fix) for n in 06 07; do require_artifact "$n"; done ;;
  hotfix) for n in 03 06 07; do require_artifact "$n"; done ;;
esac

# --- stage 4 mutation check must have run (v1.2 pre-LOCK gate) ---
if [ "$mode" = "feat" ] && [ -n "$adir" ] && ls "$adir"/04-*.md >/dev/null 2>&1; then
  # ANY 04 artifact carrying the record satisfies it (same scope as the old
  # global grep); the addition is that the record must have CONTENT.
  _m4=0
  for _f4 in "$adir"/04-*.md; do
    [ -f "$_f4" ] || continue
    section_has_body "$_f4" "뮤테이션 검증" && { _m4=1; break; }
  done
  [ "$_m4" -eq 1 ] || violation "no stage 4 artifact carries a '뮤테이션 검증' record WITH content - the phrase alone is not the check (04-test-generation.md §4-1)"
fi

# --- design amendment cumulative cap (03-design.md §9-6) ---
if [ -n "$adir" ] && ls "$adir"/03-*.md >/dev/null 2>&1; then
  amendments=$(cat "$adir"/03-*.md 2>/dev/null | grep -c "^## 변경 내역" || true)
  if [ "${amendments:-0}" -gt 2 ]; then
    violation "design artifact has $amendments amendments - cap is 2; the third change must escalate to a full stage-3 redesign (03-design.md §9)"
  fi
fi

# --- stage 7 verdict must be real, not a stub ---
# Scope to 07-review*.md only: lens finders write their raw output to
# 07-finder-<lens>.md (agent-review.md context economy) - those are evidence
# attachments, not verdicts, and must not be held to the verdict format.
if [ -n "$adir" ] && ls "$adir"/07-*.md >/dev/null 2>&1; then
  ls "$adir"/07-review*.md >/dev/null 2>&1 || violation "stage 7 artifacts exist but none matches 07-review*.md - finder files alone are not a review verdict"
fi
if [ -n "$adir" ] && ls "$adir"/07-review*.md >/dev/null 2>&1; then
  for f in "$adir"/07-review*.md; do
    [ -f "$f" ] || continue
    # per-file, not a global grep: with multiple review files (re-reviews) one
    # having the section must not cover for another missing it
    section_has_body "$f" "검증하지 못한 것" ||
      violation "stage 7 artifact has no '검증하지 못한 것' section WITH content - an empty section is not a limits record ($f)"
    # verdict = FIRST TOKEN of the first non-empty line under the LAST 판정
    # heading (re-reviews append; prose may legally mention other verdict words).
    # Template combo line is excluded so a stub never counts as filled.
    vline=$(grep -n "^#\{1,6\}[[:space:]]*판정" "$f" | tail -1 | cut -d: -f1)
    vword=""
    if [ -n "$vline" ]; then
      vword=$(sed -n "$((vline + 1)),$((vline + 5))p" "$f" | grep -vE "PASS */ *REFACTOR" | awk 'NF {print $1; exit}')
    fi
    case "$vword" in
      PASS) ;;
      REFACTOR | ESCALATE)
        violation "stage 7 verdict is $vword - the pipeline is unresolved at PR time; resolve it and re-run stage 7 to PASS ($f)"
        ;;
      *)
        violation "stage 7 artifact 판정 section is empty or still a template stub ($f)"
        ;;
    esac
    # multi-lens review must leave evidence: raw finder output attached (feat only;
    # fix/hotfix run the 7-축소 review without finders). The section must have BODY -
    # an empty heading is not evidence, and only a real HEADING anchors the section
    # (a passing mention of the phrase elsewhere must not).
    if [ "$mode" = "feat" ]; then
      fline=$(grep -n "^#\{1,6\}[[:space:]].*Finder 원출력" "$f" | tail -1 | cut -d: -f1)
      finder_body=0
      if [ -n "$fline" ]; then
        finder_body=$(sed -n "$((fline + 1)),\$p" "$f" | sed -n '/^#\{1,6\}[[:space:]]/q;p' | grep -c "[^[:space:]]" || true)
      fi
      [ "${finder_body:-0}" -gt 0 ] || violation "stage 7 artifact has no non-empty 'Finder 원출력' section - lens finders left no evidence (07-review.md)"
      # a PASS verdict on a GATE-TARGET feature requires the second-verifier record.
      # Non-gate features confirm on the first verifier's PASS (token tiering).
      if [ -n "$gate" ] && [ "$vword" = "PASS" ]; then
        grep -Eq '^#{2,6}[[:space:]].*2차 verifier' "$f" || violation "gate-target stage 7 verdict is PASS but artifact has no '2차 verifier' section (07-review.md §1-1)"
      fi
    fi
  done
fi

# --- escaped-bug feedback on bugfix paths ---
if [ "$mode" = "fix" ] || [ "$mode" = "hotfix" ]; then
  if [ -n "$dlog" ]; then
    grep -q "유출 경로" "$dlog" || violation "bugfix decision log has no '유출 경로:' line (which review lens missed it, or 'pipeline 외 기원')"
  fi
fi

# --- gate cross-check: derived gate conditions need a human decision record,
# or a pre-approved pattern that is actually registered (human-maintained file) ---
if [ -n "$base" ] && [ -n "$gate" ] && [ -n "$dlog" ]; then
  say "gate conditions re-derived from diff:$gate"
  # match without the 🧑 emoji - emoji encoding varies across tools
  if grep -q "사람 결정" "$dlog"; then
    say "human gate decision found in decision log"
  elif grep -q "사전 승인 패턴 적용" "$dlog"; then
    case "$gate" in
      *high-risk*)
        hard_violation "high-risk gate ($gate) cannot be satisfied by a pre-approved pattern - a '사람 결정' record is required (team-policy 위험 차등 게이트)"
        ;;
      *)
        pat=$(sed -n '/사전 승인 패턴 적용/{s/.*사전 승인 패턴 적용[[:space:]:]*//;s/[[:space:]]*$//;p;q;}' "$dlog")
        if [ -n "$pat" ] && grep -qF "## $pat" "$ctx/pre-approved-patterns.md" 2>/dev/null; then
          say "pre-approved pattern '$pat' verified against $ctx/pre-approved-patterns.md"
        else
          hard_violation "decision log claims pre-approved pattern '$pat' but no matching '## $pat' heading exists in $ctx/pre-approved-patterns.md - unregistered pattern claims are gate bypass"
        fi
        ;;
    esac
  else
    hard_violation "diff triggers design gate ($gate) but decision log has no '사람 결정' record"
  fi
fi

# --- enforcement self-protection: a pipeline branch that edits the audit's own
# detection surface (repo profile, audit/lock/gate scripts) can neuter gate
# re-derivation in the same PR that exploits it. Feature work has no business
# touching enforcement - demand an explicit human decision record. (Enforcement
# maintenance itself belongs on chore/ branches, where the human reviews the PR.)
if [ -n "$base" ]; then
  enf=$(echo "$changed" | grep -E "^\.agents/context/repo-profile\.sh$|^scripts/(audit/|test_lock|unlock_tests|pr_review_gate|process_audit|default_branch)" || true)
  if [ -n "$enf" ] && { [ -z "$dlog" ] || ! grep -q "사람 결정" "$dlog"; }; then
    hard_violation "pipeline branch modifies the enforcement surface without a '사람 결정' record - self-serving guard edits are gate bypass: $(echo "$enf" | tr '\n' ' ')"
  fi
fi

# drift telemetry: surface override usage in every PR's CI log (push, not pull)
if [ -d "$ctx/decisions" ]; then
  oc=$(grep -rc "override 사용" "$ctx/decisions" 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
  say "telemetry: 'override 사용' records across decision logs: ${oc:-0}"
fi

if [ "$fail" -eq 0 ]; then _dev_rec pass; say "ok"; fi
exit "$fail"
