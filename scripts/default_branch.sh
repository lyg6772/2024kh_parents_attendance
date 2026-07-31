#!/bin/sh
# Prints the remote default branch ref (e.g. "origin/master"). Single source
# for scripts and agent prompts - never hardcode the default branch name.
# Fail-closed: exits 1 if nothing resolvable.
set -u

ref=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || echo "")
if [ -z "$ref" ]; then
  for b in origin/master origin/main; do
    if git rev-parse -q --verify "$b" >/dev/null 2>&1; then
      ref=$b
      break
    fi
  done
fi
if [ -z "$ref" ]; then
  echo "default_branch: cannot resolve remote default branch (no origin/HEAD, origin/master, or origin/main)" >&2
  exit 1
fi
printf '%s\n' "$ref"
