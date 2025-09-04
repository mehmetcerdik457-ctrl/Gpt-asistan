#!/data/data/com.termux/files/usr/bin/sh
set -e
BASE="$HOME/downloads"
OUT1="$BASE/ga-memory.jsonl"
OUT2="$BASE/ga-notes.json"

# API ile üret
curl -sS -X POST http://127.0.0.1:8000/backup >/dev/null || true

# Zaman damgası ve SD kopyası
TS=$(date +%Y%m%d-%H%M%S)
DST="/sdcard/Download"
[ -d "$DST" ] || { echo "⚠️  /sdcard/Download yok. Önce: termux-setup-storage"; exit 0; }
cp -f "$OUT1" "$DST/ga-memory-$TS.jsonl"
cp -f "$OUT2" "$DST/ga-notes-$TS.json"
echo "[OK] SD: $DST/ga-memory-$TS.jsonl | $DST/ga-notes-$TS.json"

# Google Drive (rclone 'gdrive' uzak hedefi gerekir)
rclone mkdir gdrive:/GPT-Asistan-Yedek >/dev/null 2>&1 || true
rclone copy "$DST" gdrive:/GPT-Asistan-Yedek \
  --include "ga-memory-$TS.jsonl" \
  --include "ga-notes-$TS.json" >/dev/null && echo "[OK] Drive: GPT-Asistan-Yedek/"

