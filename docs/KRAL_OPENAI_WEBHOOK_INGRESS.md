# KRAL OpenAI webhook ingress

## Endpoint

The existing Gateway exposes one public webhook receiver:

- `POST /webhooks/openai`
- `Content-Type: application/json`
- No owner P-256 headers are required; the OpenAI Standard Webhooks signature is the authentication boundary for this route only.
- All other owner routes retain their existing dual P-256 authentication.

## Required server configuration

Set `OPENAI_WEBHOOK_SECRET` to the signing secret generated for the OpenAI project webhook endpoint. Keep it only in the private server environment/secret manager. Never put it in the APK, repository, issue, CI log, or client configuration.

The receiver verifies the exact raw body bytes against the `webhook-id`, `webhook-timestamp`, and `webhook-signature` headers using Standard Webhooks v1 HMAC-SHA256. It enforces a five-minute timestamp tolerance and a 64 KiB body limit.

## Delivery and idempotency

After signature and event-shape validation, KRAL durably records the delivery ID, event ID/type, receive time, and body SHA-256 in the existing SQLite database. A duplicate delivery with identical content is acknowledged with HTTP 200 and `duplicate: true`. Reuse of a delivery ID with different content is rejected with HTTP 409.

Tasks remain synchronous unless the owner explicitly sets `background: true` in the existing authenticated `POST /api/v1/owner/tasks` request. Background task submission uses the fixed OpenAI Responses endpoint with `background: true` and `store: false`; KRAL persists the response ID and waits for a signed `response.completed`, `response.failed`, or `response.incomplete` webhook. On completion, KRAL retrieves only the response ID already bound to that task, validates the returned model and output, and commits the result to the existing task record. Webhook processing occurs before the delivery receipt is committed so transient retrieval failures receive a non-2xx response and can be retried.

Background responses are temporarily stored by OpenAI for roughly 10 minutes to support polling and webhook retrieval. KRAL explicitly sets `store: false`; it does not opt into 30-day response storage. KRAL does not execute model tools, shell commands, GitHub writes, or other external actions. A cancelled task discards any later webhook result; cancellation does not stop the remote OpenAI computation. Background mode is opt-in per task; existing task submissions retain synchronous behavior. The request cannot combine `background: true` with `requires_approval: true`.

## Verification

Run the repository's server test suite, including `server/tests/test_openai_webhooks.py`. Tests use synthetic signing secrets, fake providers, and synthetic response events; they do not contact OpenAI or prove that a production webhook endpoint has been configured. Background mode must not be enabled in production until the project webhook is configured with the matching private signing secret.

For local endpoint testing, use OpenAI's dashboard test delivery or the documented test endpoint. Do not expose a development server without HTTPS and an explicit access boundary.
