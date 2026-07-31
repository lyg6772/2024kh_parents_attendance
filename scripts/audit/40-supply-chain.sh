#!/bin/sh
# Supply-chain guard: new direct dependencies must be real PyPI packages.
# The ONLY networked check - isolated here so a PyPI/network flake is
# identifiable at a glance instead of reddening the whole audit anonymously.
#
# Slopsquatting: agents hallucinate package names, and a gate approver who
# doesn't read code cannot tell a typosquat from the real thing. Scope: direct
# deps in pyproject.toml (transitives resolve from real packages via uv.lock).
CHECK="supply-chain"
. "$(dirname "$0")/lib.sh"

if [ "$mode" = "nonpipeline" ]; then _dev_rec n/a "nonpipeline-branch"; exit 0; fi

# this check parses pyproject.toml and queries PyPI - other ecosystems need
# their own port (repo profile declares which one applies; see .agents/PORTING.md)
if [ "${PKG_ECOSYSTEM:-}" != "python-uv" ]; then
  _dev_rec skip "profile-off"
  say "repo profile PKG_ECOSYSTEM='${PKG_ECOSYSTEM:-}' is not python-uv - skipping (declared, not silent)"
  exit 0
fi

# TOML-parse every dependency location (project.dependencies, all
# optional-dependencies groups, all dependency-groups, inline arrays included) -
# an awk line-scanner missed one-line arrays and non-dev groups.
dep_names() {
  git show "$1:pyproject.toml" 2>/dev/null | python3 -c '
import re, sys, tomllib
d = tomllib.loads(sys.stdin.read())
names = set()
def add(dep):
    if not isinstance(dep, str): return
    # URL/git/VCS-sourced deps are NOT PyPI-verifiable - the name before @ lies
    # about where the code comes from. Emit a sentinel so the caller fails closed.
    if "@" in dep or "://" in dep:
        names.add("!URLSOURCE:" + dep.strip().split()[0].lower())
        return
    m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", dep.strip())
    if m: names.add(m.group(0).lower())
for dep in d.get("project", {}).get("dependencies", []): add(dep)
for group in d.get("project", {}).get("optional-dependencies", {}).values():
    for dep in group: add(dep)
for group in d.get("dependency-groups", {}).values():
    for dep in group: add(dep)
for dep in d.get("build-system", {}).get("requires", []): add(dep)
# [tool.uv.sources] redirects a named dep to a git/url/path - also not PyPI
for name, src in d.get("tool", {}).get("uv", {}).get("sources", {}).items():
    names.add("!URLSOURCE:" + str(name).lower())
print("\n".join(sorted(names)))
' 2>/dev/null
}

if [ -n "$base" ] && echo "$changed" | grep -q "^pyproject.toml$"; then
  if ! command -v python3 >/dev/null 2>&1; then
    violation "python3 unavailable - supply-chain check cannot parse pyproject.toml (fail closed: verify new dependencies manually)"
  fi
  old_deps=$(dep_names "$base")
  new_deps=$(dep_names HEAD)
  if [ -z "$new_deps" ] && command -v python3 >/dev/null 2>&1; then
    violation "pyproject.toml changed but dependency parse returned nothing - malformed TOML? supply-chain check cannot vouch for new dependencies (fail closed)"
  fi
  for d in $new_deps; do
    # -F: compare package names literally (e.g. "ruamel.yaml" is not a regex)
    echo "$old_deps" | grep -Fqx "$d" && continue
    case "$d" in
      "!URLSOURCE:"*)
        pkg=${d#!URLSOURCE:}
        hard_violation "new dependency '$pkg' is sourced from a URL/git/[tool.uv.sources] target, not PyPI - the package name cannot be verified against its origin; record a 사람 결정 with the exact source and why it is trusted"
        continue
        ;;
    esac
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://pypi.org/pypi/$d/json" 2>/dev/null || echo 000)
    # transient errors (429/5xx/network): one retry before judging
    case "$code" in
      200|404) ;;
      *) sleep 2; code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://pypi.org/pypi/$d/json" 2>/dev/null || echo 000) ;;
    esac
    case "$code" in
      404)
        hard_violation "new dependency '$d' does NOT exist on PyPI - hallucinated or typosquatted package (slopsquatting guard)"
        ;;
      200)
        if command -v jq >/dev/null 2>&1; then
          # both [] optional: a missing/null .releases must not abort the filter
          created=$(curl -s --max-time 10 "https://pypi.org/pypi/$d/json" 2>/dev/null | jq -r '[.releases[]?[]?.upload_time] | sort | .[0] // empty' 2>/dev/null)
          # date -d is GNU-only (empty on macOS/BSD -> false positive). python3 is
          # already a hard dep of this script, so parse the ISO ts portably there.
          created_epoch=$(python3 -c 'import datetime,sys
s=sys.argv[1]
if not s: raise SystemExit(1)
print(int(datetime.datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()))' "${created:-}" 2>/dev/null || echo "")
          if [ -z "$created_epoch" ]; then
            # no parsable release metadata = reserved/empty package (classic
            # squatting shape) - fail closed, same class as the 404 case
            violation "new dependency '$d' exists on PyPI but has no parsable release metadata (reserved/empty package?) - verify provenance and record a 사람 결정"
          elif [ $(($(date +%s) - created_epoch)) -lt 7776000 ]; then
            violation "new dependency '$d' is younger than 90 days on PyPI (first upload $created) - typosquat risk; record an explicit 사람 결정 with the package's provenance"
          else
            say "supply-chain: new dependency '$d' verified on PyPI"
          fi
        else
          say "supply-chain: new dependency '$d' exists on PyPI (age check skipped - no jq)"
        fi
        ;;
      *)
        violation "PyPI check inconclusive for new dependency '$d' (HTTP $code after retry) - verify the package manually and record a 사람 결정 (fail closed)"
        ;;
    esac
  done
fi

if [ "$fail" -eq 0 ]; then _dev_rec pass; say "ok"; fi
exit "$fail"
