# KRAL OpenAI guide adapter

This change adapts the supplied **Build the OpenAI Integration for KRAL** guide
to the existing Python backend. It introduces no new service, dependency, model
default, credential, or Android OpenAI client. The existing signed gateway gains
local tool proposal/status/approval/cancellation routes.

## Existing service boundary

Existing Android service `OwnerGateway.submitTask()` → signed
`POST /api/v1/owner/tasks` → `TaskManager` →
`OpenAIProvider.reply_with_metadata()` → OpenAI Responses API.

The adapter keeps the fixed HTTPS endpoint, server-side key, configured model
allowlist, dual-P256 owner/device authorization, output bounds, `store: false`,
and existing Android result schema. The guide's default model is an example;
this change does not assume account access or insert it into the allowlist.

Injected providers exposing `reply_with_metadata()` must accept the new
`system_instructions` keyword. Legacy providers exposing only `reply()` retain
their existing combined-prompt path. A failed call is not retried through another
method, which avoids accidentally repeating an upstream request.

## Acceptance map

| Guide behavior | Existing-contract implementation | Automated evidence |
| --- | --- | --- |
| Separate app policy from user input | Responses input has distinct `system` and `user` messages; specialist instructions come from the backend | Provider request-shape tests; task lifecycle tests; signed HTTP task test with mocked upstream |
| Correlate each task | `metadata.request_id`, existing `kral_task_id`, and `X-Client-Request-Id` carry the task ID | Provider metadata tests; signed HTTP task test |
| Stable result and response ID | Android retains `result`, `model`, `response_id`; provider rejects missing/malformed response IDs | Success and response-ID validation tests |
| Missing key and typed access errors | Existing `PROVIDER_NOT_CONFIGURED`, `PROVIDER_AUTH_DENIED`, `PROVIDER_MODEL_OR_PERMISSION_DENIED`, `PROVIDER_MODEL_NOT_AVAILABLE` | Mocked missing-key, 401, 403 and 404 tests |
| No unapproved tool side effects | AI task route still rejects tools; separate fixed local capability registry requires exact signed approval for `memory.save` | Signed task rejection tests; tool policy and signed HTTP tests |
| Approval binds the exact action | Proposal digest binds actor, device/key identity, tool, arguments, scope, policy and expiry | Tampered approval, actor rebinding, replay, cancellation and expiry tests |
| Approved execution with evidence | Local memory write and approval/completion audit commit once in the same SQLite transaction | Signed approved execution, concurrency, rollback and restart tests |

## Reproduce the offline checks

From the existing repository checkout (do not create another project):

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r server/requirements.txt
.venv/bin/python -m unittest discover -s server/tests -v
git diff --check
```

The tests use synthetic keys, temporary databases, local HTTP requests, and
mocked OpenAI responses. No API key or paid provider call is needed. A passing
mocked request is not proof of account/model access or a deployed Android flow.

## Verification in this workspace

Base commit: `5e87bdbfcd460d3e1152662ed20f254d8474bc21` from
`integration/kral-genesis-task-runtime-20261103`.
Working branch: `codex/kral-openai-guide-adapter`.

| Check | Result |
| --- | --- |
| Focused gateway and task runtime suites | 50 tests passed |
| Focused local tool-policy suite | 15 tests passed |
| `.venv/bin/python -m unittest discover -s server/tests -v` | 152 tests passed; no failures or skips |
| Android JVM suite | 63 passed, 6 existing native/Keystore cases ignored on JVM and exercised on the emulator |
| Android lint and app/test APK builds | Passed; lint has 0 errors and 31 warnings |
| Configured HTTPS gateway emulator acceptance | 4 passed, no failures/skips, no external provider calls |
| `git diff --check` | Passed |
| Configured API key, model allowlist/preference and owner/device identity variables | Not set in this workspace; synthetic fixtures used |
| Billable OpenAI calls, physical-device checks and deployment | Not run |

Changed files:

- `server/gateway.py`: structured policy/user input and required response ID.
- `server/task_runtime.py`: separate specialist policy and task correlation.
- `server/tests/test_gateway.py`: provider contract and signed HTTP regressions.
- `server/tests/test_task_runtime.py`: specialist-policy and metadata coverage.
- `server/tool_tasks.py`: durable local capability policy and exact approvals.
- `server/tests/test_tool_tasks.py`: signed approval and transaction coverage.
- `docs/KRAL_OPENAI_MODEL_ACCESS.md`: updated adapter behavior.
- `docs/KRAL_OPENAI_GUIDE_ADAPTER.md`: acceptance map and verification record.
- `docs/KRAL_TOOL_TASKS.md`: capability policy and signed API usage.

Dependency declarations and `owner_auth_v1.py` signature verification are
unchanged. The Android owner signer now accepts the four local tool routes;
the existing gateway client validates immutable proposals and signs explicit
approvals. UI and default TLS/Keystore signing remain unchanged. Current source,
delivery status and the complete acceptance record are in
[KRAL_OCT26_ACCEPTANCE.md](KRAL_OCT26_ACCEPTANCE.md).

## Remaining scope

The [local tool boundary](KRAL_TOOL_TASKS.md) supports `status` reads and
single-use approved `memory.save` execution. Existing AI task approval retains
its earlier record-only behavior. General model function-calling/resume loops,
additional capabilities and an Android approval screen are not implemented.

The separate signed local worker endpoint retains its existing read-only
allowlist. Its access to local memory does not authorize sending that memory to
OpenAI.

Live API readiness, physical-device acceptance, deployment and publication
remain separate checks. In particular, the signed `models` route
can issue billable Responses probes; do not use it as a free readiness check.
