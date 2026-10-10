#!/usr/bin/env bash
# rclone ile Google Drive'a senkronizasyon.
# Env: RCLONE_REMOTE (varsayılan: gdrive), DRIVE_PATH (varsayılan: gpt-asistan-backup), BACKUP_SOURCE (varsayılan: .)
# rclone yapılandırması: `rclone config` veya RCLONE_CONFIG_* env değişkenleri.
set -euo pipefail
command -v rclone >/dev/null || { echo "rclone kurulu değil" >&2; exit 1; }
SRC="${BACKUP_SOURCE:-.}"
DEST="${RCLONE_REMOTE:-gdrive}:${DRIVE_PATH:-gpt-asistan-backup}"
rclone sync "$SRC" "$DEST" \
  --exclude ".git/**" --exclude ".env" --exclude "build/**" \
  --exclude ".gradle/**" --exclude "node_modules/**" --progress
