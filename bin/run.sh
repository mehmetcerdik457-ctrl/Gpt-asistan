#!/data/data/com.termux/files/usr/bin/sh
set -e
cd ~/repos/gpt-asistan
export PYTHONPATH=src
termux-wake-lock || true
exec python -m uvicorn gpt_asistan.app:app --host 0.0.0.0 --port 8000 --http h11 --loop asyncio --reload
