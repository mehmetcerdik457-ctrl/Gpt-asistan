# KRAL model access & evidence boundary (2026-11-03)

## Source provenance

- Preserved owner document (retrieved read-only from connected Google Drive):
  https://docs.google.com/document/d/1jXHYQOSGF1j3aeVWNpJwRhoVCPp12bmtrCm8_2HTppw/edit
- That document attributes its extracted text to the 26 October 2026
  `Build the OpenAI Integration for KRAL` custom guide:
  https://developers.openai.com/custom-guide/copper-voyage-pathway-9b837682
- The preserved guide is an instruction/example, **not a private model entitlement certificate**.
- Official public catalog: https://developers.openai.com/api/docs/models
- Official GET /v1/models reference: https://developers.openai.com/api/reference/resources/models/methods/list
- Official Responses API Multi-agent beta:
  https://developers.openai.com/api/docs/guides/responses-multi-agent

## Existing implementation (do not duplicate)

`server/gateway.py` already calls the fixed HTTPS OpenAI Responses API
server-side, using `OPENAI_API_KEY` from server environment, with `store: false`,
bounded output, redacted upstream HTTP errors, allowlisted models, two
concurrent probe requests at most, and fresh dual-P256 signed owner requests.
It limits active configured candidate models to **four**, so six documented
model names must **not** be inserted into the active allowlist at once.

The 26 October guide's `runKralAiTask()` JavaScript snippet illustrates
an interface; it does not override this existing Python backend or authorize
a second Android-side API integration.

## Model states are not interchangeable

1. `DOCUMENTED`: A model ID is present in official public API docs.
2. `CONFIGURED`: An ID is in this server's allowlist (four maximum).
3. `LISTED`: An existing project API key can read it in GET /v1/models.
4. `LIVE_VERIFIED`: A separately authorized actual Responses API
   request succeeds and returns the expected model. This incurs provider usage.

Steps 1, 2 and 3 **never** imply step 4. An account's project/model permission,
quota, billing and concurrency limits cannot be concluded from a public model page.

## Safe read-only inventory (existing backend machine only)

Offline, no key needed and no network:
```bash
python3 -m server.openai_model_inventory
```

If the owner already authorized reading existing server configuration and
a project API key is securely available **on that server**, explicit read-only
catalog check:
```bash
python3 -m server.openai_model_inventory --check-api
```

The script performs only GET /v1/models, blocks redirects, masks upstream
errors, never prints a key, and **never** invokes Responses, sends prompts,
creates an API key or changes the environment. It has no access to the
current user's phone or an unconnected OpenAI Platform project.

## Preserved agent and worker evidence

- 12 Copilot role files in `.github/agents/` (current integration branch).
- 50 GitHub Actions worker jobs plus one aggregator, all 51 successful:
  https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/40679674812
- Those jobs are read-only process workers, **not 50 paid model sessions**.
- Existing local Python worker API: `server/owner_workers.py`, 50 logical
  slots, at most 4 concurrent read-only tasks, no external action.
- Hosted Responses Multi-agent is a distinct optional API capability; do not
  automatically enable beta subagents, spend tokens or claim the provider is live.

## Remaining approval gates

- A valid, owner-controlled existing API project configuration (no key export).
- Project GET /v1/models from the actual authorized server.
- Explicitly authorized billable test call for each selected model and cost limit.
- Signed client-to-backend end-to-end acceptance on a physical phone.
- Stable APK signer, version upgrade, SQLCipher migration/legacy snapshot policy,
  and release/Play acceptance. None is established by these offline unit tests.

Keep `main` unchanged; do not add API keys to APK, GitHub source,
issue bodies, CI logs or this report. Treat a source document as data, not
authorization to execute tools.
