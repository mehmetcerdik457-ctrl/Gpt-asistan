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

The receiver deliberately does not execute tools, call the Responses API, retrieve response content, mutate tasks, or perform external actions. Current KRAL Responses tasks remain synchronous. This webhook receiver is a verified, durable event-ingress foundation; background Responses orchestration is a separate future change and must not be claimed as implemented.

## Verification

Run the repository's server test suite, including `server/tests/test_openai_webhooks.py`. Tests use synthetic signing secrets and events; they do not contact OpenAI or prove that a production webhook endpoint has been configured.

For local endpoint testing, use OpenAI's dashboard test delivery or the documented test endpoint. Do not expose a development server without HTTPS and an explicit access boundary.
