# KRAL Genesis 3.0 — Sol / WAL / idempotency / local workers

Scope: Reviewable integration branch. No owner/device enrollment, SQLite data, GitHub Actions runners, billing, secret value or production deployment is modified.
Original KRAL guide: https://developers.openai.com/custom-guide/copper-voyage-pathway-9b837682

## Model
gpt-5.6-sol is a documented Responses API model identifier; it is not proof of account access.
server/config.env.example shows OPENAI_ALLOWED_MODELS=gpt-5.6-sol and OPENAI_MODEL_PREFERRED=gpt-5.6-sol.
OpenAIProvider.candidates() prioritizes a preferred model ONLY if it exists in the approved allowlist.
The signed /api/v1/owner/models route still requires a genuine provider response for model verification. Never infer an account quota or successful call.

## Existing persistence
server/gateway.py uses SQLite WAL and private storage.
server/kral_memory.py uses FTS5 + sqlite-vec plus reciprocal-rank fusion, with explicit memory opt-in.
server/idempotency.py uses SHA-256 request hashes and an SQLite processing/completed/failed ledger with BEGIN IMMEDIATE.
server/owner_auth_v1.py requires separate owner and device P-256 signatures and a persistent single-use nonce.

## Bounded read-only local workers
POST /api/v1/owner/workers uses the original dual P-256 signed HTTP gateway.
Sample JSON:
{
 "max_parallel": 4,
 "tasks": [
   {"id":"W01","kind":"status","args":{}},
   {"id":"W02","kind":"models.cached","args":{}},
   {"id":"W03","kind":"memory.search","args":{"query":"not","limit":3}}
 ]
}
Allowlist: status, models.cached, history.recent, memory.search.
Capacity: 1–50 uniquely named logical slots W01–W50; at most four concurrent local threads. Every job is validated before any executes.
No shell, model request, GitHub mutation, external export, paid tool, merge or auto-approval path exists in this endpoint.
The separate GitHub 50-worker branch holds source-bound read-only process checks; they are NOT 50 independently operating external LLM models and are not silently merged here.

## Test commands and acceptance
GitHub Actions CI: python -m unittest discover -s server/tests -v
Android candidate workflow remains unchanged.
New tests exercise signed HTTP requests, 50 logical slots, memory search, WAL persistence, SHA-256 idempotency replay, no unauthorized model preference and denied writing tools.
All tests use synthetic credentials and model responses; a passing CI is not a production HTTP 200.

Outstanding acceptance: trusted enrollment of real owner/device public keys, an explicit approved production deploy, live OpenAI quota/response verification, and real Android hardware signed request. Previously observed Railway error: "Your trial has expired." No claim of a successful Railway deployment.
