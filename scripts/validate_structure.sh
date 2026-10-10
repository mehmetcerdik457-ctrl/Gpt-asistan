#!/usr/bin/env bash
# Validates monorepo layout, python syntax, and obvious secret leaks.
set -u
cd "$(dirname "$0")/.."
fail=0
for d in core agents integrations apps tools archive docs backup evidence; do
  [ -d "$d" ] || { echo "MISSING dir: $d"; fail=1; }
done
for f in README.md MANIFEST.md .env.example docs/INVENTORY.md docs/API_DISCOVERY.md docs/SECURITY_FINDINGS.md docs/KNOWN_ISSUES.md docs/MIGRATION_REPORT.md; do
  [ -f "$f" ] || { echo "MISSING file: $f"; fail=1; }
done
grep -qxF '.env' .gitignore 2>/dev/null || { echo ".env not in .gitignore"; fail=1; }
while IFS= read -r f; do
  python3 -m py_compile "$f" || fail=1
done < <(git ls-files '*.py' 2>/dev/null; git ls-files --others --exclude-standard '*.py' 2>/dev/null)
if grep -rEn --exclude-dir=.git --exclude-dir=docs --exclude=validate_structure.sh '(sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|ghp_[A-Za-z0-9]{30,})' .; then
  echo "possible hard-coded secret"; fail=1
fi
find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
[ $fail -eq 0 ] && echo "OK: structure valid" || { echo "FAILED"; exit 1; }
