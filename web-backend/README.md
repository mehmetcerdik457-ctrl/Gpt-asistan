# OMEGA Vercel Web Backend

Vercel root directory: `web-backend/`. This is an isolated Next.js App Router backend.
It does not replace or modify the existing Android app, `server/`, `worker_fleet/`,
`kral/mcp/youtube_server.py`, or the PWA branch.

## Safety and runtime contracts

- All workflow endpoints require `Authorization: Bearer $OMEGA_API_TOKEN`.
- Workflow state is stored in PostgreSQL via `DATABASE_URL`; no serverless local-disk persistence.
- Approval decisions are HMAC-authenticated with `OMEGA_APPROVAL_SECRET`.
- Model calls use the configured OpenAI Responses API only; missing configuration fails closed.
- YouTube writes remain disabled. `YOUTUBE_WRITE_ENABLED=false` is the required baseline.
- Metadata/transcript require a separately deployed worker HTTP adapter. The repository's current
  yt-dlp/FFmpeg pipeline is a local CLI, not an HTTP service; these routes return
  `503 YOUTUBE_WORKER_NOT_CONFIGURED` until a real adapter is deployed.
- Analytics uses the read-only YouTube Analytics API and OAuth refresh-token credentials.
- Secrets are read only from environment variables. No credential values belong in Git.

## Existing Python gateway compatibility

`server/gateway.py` requires a persistent private volume and dual P-256 owner/device
signatures. It is not silently proxied or weakened by this Vercel service. A dedicated
adapter is required before Vercel can invoke protected owner operations.

## Routes

- `POST /api/workflows/start`
- `POST /api/workflows/approval/[taskId]`
- `POST /api/workflows/cancel/[runId]`
- `POST /api/callbacks/[token]`
- `GET /api/youtube/metadata?url=...`
- `GET /api/youtube/transcript?url=...`
- `GET /api/youtube/analytics?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&metrics=...`

## Local checks

Run `npm ci`, `npm run typecheck`, and `npm run build` from this directory.
A live database, OAuth consent, worker adapter, and Vercel deployment are separate
integration checks and are not claimed by a successful static build.
