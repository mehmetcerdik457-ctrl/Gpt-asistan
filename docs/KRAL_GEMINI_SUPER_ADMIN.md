# KRAL Gemini and SUPER ADMIN control-plane slice

## What this branch adds

- A server-only Gemini adapter using the Google Gemini Interactions API.
- Deterministic provider selection: `gemini-*` model IDs route to Gemini; other configured model IDs route to OpenAI.
- A shared maximum of four configured model candidates. Provider failure does not silently fall back to another provider.
- Gemini requests send `store: false`; the API key is read only from `GEMINI_API_KEY` in the private server environment.
- A read-only `POST /api/v1/owner/admin/status` endpoint, protected by the existing dual P-256 owner/device request authentication.
- An Android entry point labelled “SUPER ADMIN / Bağlantı durumu”.

## Gemini configuration

Set these only in the private backend environment:

- `GEMINI_API_KEY`
- `GEMINI_API_VERSION` — `v1beta` by default; choose `v1` only after verifying that the selected model is available on stable v1.
- `GEMINI_ALLOWED_MODELS` — comma-separated explicit model allowlist; no model is assumed.
- `GEMINI_MODEL_PREFERRED` — optional preference that must also appear in the allowlist.

The provider calls `POST https://generativelanguage.googleapis.com/{GEMINI_API_VERSION}/interactions` with the `x-goog-api-key` header. It defaults to `v1beta`, the version shown by Google's default Interactions API reference; stable `v1` is available but model support can differ. The version is constrained to `v1beta` or `v1`. Use a current Gemini authorization API key from the intended Google AI Studio/Cloud project; do not use an unrestricted legacy standard key. The model-verification request is a real provider request and may incur usage charges. Google documents Interactions as its recommended interface for new Gemini integrations; model IDs and project access still need to be verified against the actual configured project.

Gemini background task/webhook support is deliberately rejected in this slice. Existing OpenAI background Responses and webhook processing remain OpenAI-only. Gemini requests are synchronous and only run after the existing model-verification flow.

## SUPER ADMIN status contract

The status endpoint returns:
- `role=SUPER_ADMIN` for the authenticated single-owner control plane;
- provider configuration state and candidate counts, never secret values;
- currently live-verified model snapshots;
- explicit `NOT_CONFIGURED_IN_KRAL_BACKEND` states for Google Cloud, Google Drive, and GitHub Actions;
- flags showing that model tools and external actions remain disabled.

This is a read-only status panel, not yet a full connector/OAuth/role-management console. It does not grant Google Cloud, Drive, GitHub Actions, or ChatGPT connector access. It does not create, rotate, display, or write API keys. It does not modify provider configuration.

## Not yet verified

- No Gemini key was present or tested during this code change.
- No live Gemini request, paid model probe, Google Cloud project access, Vertex AI ADC, Google Drive OAuth, or Google Workspace API action was performed.
- No GitHub Actions secret was read or modified.
- The Android panel is not a production admin console until the new exact-head CI and Android workflows pass.
- No APK was published and no `main` merge was performed.

## Official API references

- Gemini Interactions API: https://ai.google.dev/api/interactions-api
- Interactions overview and REST examples: https://ai.google.dev/gemini-api/docs/interactions-overview
- Gemini API key authentication: https://ai.google.dev/gemini-api/docs/generate-content/api-key

## Verification

Run the exact branch CI:
```bash
python -m unittest discover -s server/tests -v
```

The new tests use synthetic credentials and mocked HTTP responses. They do not contact Google or prove project entitlement.
