# KRAL OpenAI guide adapter

The existing signed owner chat route now calls `runKralAiTask` in
`server/gateway.py`. This Python adapter implements the guide's backend
Responses API example through the existing fixed-endpoint transport.

The trusted system instruction is the guide's exact text:

> You are the OpenAI task engine for this app. Follow existing app policy, avoid side effects unless approved, and return concise results.

Its UTF-8 SHA-256 is
`56999020c0a3fe33352c32009e918ad7b0a6b7d339814b7526a5c416492365aa`.
It is sent in the Responses `instructions` field. User text, opted-in history
and memory remain in `input`; callers cannot replace the trusted instruction.

The internal adapter accepts `userMessage` and `requestId`, calls the provider
once, and returns `text`, the actual returned `model`, and `responseId` from
the provider's response. It never generates a replacement provider response ID.
The existing HTTP route generates its own request UUID, sends it as
`metadata.request_id`, and returns the same value as `request_id`.

`OPENAI_API_KEY` stays server-side. `OPENAI_MODEL` remains configurable and
defaults to the project-approved full `gpt-4.1`. The guide's example model
does not establish account access to that model. Explicit model choice,
dated snapshot handling, and no retry or downgrade after quota errors remain.

Missing provider configuration is `OPENAI_NOT_CONFIGURED` on the guide path.
Upstream 401 is `OPENAI_ACCESS_DENIED`; upstream 403/404 is
`OPENAI_MODEL_NOT_AVAILABLE`. Existing outer provider-error HTTP mapping and
redaction remain distinct from local owner authentication failures. Insufficient
quota still returns the existing Turkish billing guidance without a fallback.

No new unauthenticated endpoint or arbitrary tool executor was added. The
existing owner/device signatures, nonce checks, private owner storage binding,
request limits and opt-in provider controls still apply. Unsupported tool or
approval fields are rejected; the system prompt alone does not authorize a
side effect, grant OpenAI administration, or create account credits.

Run the guide tests together with the existing gateway/model regressions:

```sh
python -m pytest -q server/tests/test_kral_docs_adapter.py \
  server/tests/test_openai_model_selection.py server/tests/test_gateway.py
```

These tests use synthetic provider responses. A deployed health response or a
mock HTTP 200 is not evidence of a paid live inference response. Live acceptance
requires a successful authenticated deployment and an actual provider result.
