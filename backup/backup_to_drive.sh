#!/usr/bin/env bash
# rclone-based backup. Requires a configured rclone remote (default name: gdrive).
# Usage: backup/backup_to_drive.sh [source_dir] [remote:path]
set -euo pipefail
SRC="${1:-.}"
DEST="${2:-${RCLONE_REMOTE:-gdrive}:Gpt-asistan-backup}"
command -v rclone >/dev/null || { echo "rclone not installed" >&2; exit 1; }
rclone copy "$SRC" "$DEST" \
  --exclude ".git/**" --exclude ".env" --exclude "**/build/**" \
  --exclude ".gradle/**" --exclude "*.apk" --exclude "*.db" --progress
