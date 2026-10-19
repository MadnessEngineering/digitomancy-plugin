#!/usr/bin/env bash
# Copy the shareable subset of this repo into a public checkout, then refuse
# if anything private slipped in. Usage: scripts/export_public.sh <public-checkout>
#
# Allow-list only: personal workspace files (devices.yaml, maps/, routines/,
# catalog/, CLAUDE.md, .mcp.json) never leave. scripts/public_denylist.txt
# (private, never exported) holds strings that must not appear publicly.
set -euo pipefail
cd "$(dirname "$0")/.."
dest=${1:?usage: export_public.sh <public-checkout>}
[ -d "$dest/.git" ] || { echo "not a git checkout: $dest" >&2; exit 2; }

ALLOW=(src tests plugin docs/TASKER.md scripts/build_plugin.sh scripts/export_public.sh
       pyproject.toml uv.lock LICENSE README.md .gitignore)

# mirror: delete files in dest that the allow-list no longer has (but keep .git)
find "$dest" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
for p in "${ALLOW[@]}"; do
  mkdir -p "$dest/$(dirname "$p")"
  rsync -a --exclude '__pycache__' --exclude '*.pyc' "$p" "$dest/$(dirname "$p")/"
done

fail=0
if [ -f scripts/public_denylist.txt ]; then
  if grep -rInF -f <(grep -vE '^\s*(#|$)' scripts/public_denylist.txt) "$dest" --exclude-dir=.git; then
    echo "^^ denylisted strings in export" >&2; fail=1
  fi
else
  echo "warning: no scripts/public_denylist.txt; only generic secret scan ran" >&2
fi
if grep -rInE '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|BEGIN [A-Z ]*PRIVATE KEY|xox[abp]-[0-9A-Za-z-]{10,})' "$dest" --exclude-dir=.git --exclude=uv.lock; then
  echo "^^ secret-looking strings in export" >&2; fail=1
fi
[ $fail -eq 0 ] && echo "exported $(cd "$dest" && git status --short | wc -l | tr -d ' ') changed paths to $dest; scans clean"
exit $fail
