#!/usr/bin/env bash
# Monorepo yapısını doğrular.
set -u
cd "$(dirname "$0")/.."
fail=0
for p in README.md MANIFEST.md .gitignore backup/backup_to_drive.py backup/backup_to_drive.sh backup/requirements.txt backup/README.md .github/workflows/backup-drive.yml; do
  [ -e "$p" ] || { echo "EKSİK: $p"; fail=1; }
done
for d in projects/*/; do
  [ -n "$(ls -A "$d")" ] || { echo "BOŞ: $d"; fail=1; }
done
python3 -m py_compile backup/backup_to_drive.py || fail=1
bash -n backup/backup_to_drive.sh || fail=1
[ $fail -eq 0 ] && echo "OK" || { echo "Doğrulama başarısız"; exit 1; }
