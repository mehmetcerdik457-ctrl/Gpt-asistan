# KRAL 50-worker and studio pipeline

## Runtime truth
The registry contains exactly 50 deterministic local worker slots across seven groups. These are process/task roles, not 50 live LLM agents. Unconfigured adapters return NOT_CONFIGURED. No model calls or external side effects are fabricated. Dispatch concurrency defaults to four and is capped at eight.

## Groups
- GitHub (5): repository, PR, issue, branch and release inventory.
- Drive/Owner (5): metadata, policy, secret hygiene, access review and evidence ledger.
- Coding (10): Python/Android builds, scaffolding, dependency/API/refactor/lint/type checks.
- Analysis/Test (10): unit/integration/regression, security, coverage, benchmark, logs, failure triage, doctor and reports.
- YouTube (5): yt-dlp metadata/subtitle retrieval; faster-whisper is optional for local transcription.
- Media (10): FFmpeg/FFprobe, Pillow and OpenCV processing.
- Studio (5): scene manifests, timeline, render queue, asset catalog and export.

## Commands
- python -m worker_fleet.cli status
- python -m worker_fleet.cli list
- python -m worker_fleet.cli doctor
- python -m worker_fleet.cli run worker-01 worker-21 --concurrency 2
- python -m pytest -q
- python -m ruff check worker_fleet tests/test_worker_fleet.py
- python -m bandit -r worker_fleet

## Open-source stack
yt-dlp; FFmpeg/FFprobe; faster-whisper; Pillow; OpenCV; pytest; Ruff; Bandit; pip-audit. Optional Python packages are listed in requirements-worker-pipeline.txt. FFmpeg is installed separately with the operating system package manager. Doctor is read-only and automatic repair is disabled.

Google Drive OAuth, GitHub write scopes, local model endpoint and cloud media credentials are not embedded. Add narrowly scoped adapters and secrets before enabling those external actions. CI runs tests, lint, Bandit and uploads fleet/doctor JSON reports. It does not use release signing secrets.
