# KRAL 26 October OpenAI integration acceptance

Overall acceptance is **BLOCKED**, not 100% complete: no authorized OpenAI key
or active model allowlist is configured in this environment. No paid Responses
request has been authorized or performed. Test fixture response IDs are not
live OpenAI evidence.

The implementation follows the owner-supplied text of
[Build the OpenAI Integration for KRAL](https://developers.openai.com/custom-guide/copper-voyage-pathway-9b837682).
It extends the existing Python gateway and existing Android client. No second
gateway, unrelated worker infrastructure, production deployment or main-branch
merge is introduced.

## Acceptance stages

| Stage | Status | Source and evidence |
| --- | --- | --- |
| A. OpenAI integration boundary | PASS | `server/openai_config.py`, `server/gateway.py`, `OwnerGateway.kt`: server-only credential selection, fixed HTTPS upstream, enrolled owner/device signatures; Android never receives a provider key |
| B. Responses backend adapter | PASS (offline contract) | `test_gateway.py`, `test_task_runtime.py`, `test_security_boundaries.py`: separate system/user input, correlated request IDs, required response ID, typed 401/403/404, timeout, redacted failures and no POST replay |
| C. Real API and model access | BLOCKED | Actual readiness reports `PROVIDER_NOT_CONFIGURED` and an empty configured-model list; no model-list request was sent, zero Responses attempts, no real response ID |
| D. Safe tools and owner approval | PASS (synthetic acceptance) | `tool_tasks.py`, `test_tool_tasks.py`: fixed allowlist/schemas, exact actor/tool/arguments/scope/digest/expiry binding, pending approval, atomic approved write/audit, cancellation, replay and concurrency protection |
| E. Tests and engineering evidence | PASS (offline engineering) | 152 Python tests; 63 JVM passes with 6 native-only ignores; all 17 emulator tests and all 4 strict gateway acceptance tests pass; source/artifact hashes recorded |

## Implementation and preservation

The work is based on `integration/kral-genesis-task-runtime-20261103`. Upstream
advanced during this task; commit
`057606ccfe3c5d1530022842b1901bd60a00367f` was merged into the working branch
without discarding the newer Android response provenance, typed retry errors or
the existing UI. Working branch: `codex/kral-openai-guide-adapter`.

Tested implementation commit:
`5f9ba026c4a9ef62beb617483aa34932695e3206`.
The [machine-readable evidence](evidence/kral-oct26-acceptance.json) records exact
source hashes, changed files, APK hashes, suite counts and redacted live-readiness
status. Subsequent documentation commits do not change that tested source.

- Provider model candidates remain server-allowlisted. The guide's example model
  is not automatically selected and public catalog documentation does not prove
  account entitlement.
- Existing `OPENAI_API_KEY` has priority. Managed environments may instead bind
  `KRAL_OPENAI_API_KEY` securely to `api.openai.com`; no credential value belongs
  in source, Android, PR text or evidence.
- Task and chat calls send `metadata.request_id` and `X-Client-Request-Id`.
  Existing result fields and Android typed error contracts are preserved.
- Unknown upstream error codes and invalid/secret-bearing request IDs are
  omitted. A configured key reflected in response text/model/ID is rejected.
- [Local tool policy](KRAL_TOOL_TASKS.md) supports only `status` and owner-approved
  `memory.save`. It does not authorize shell, external services, spending money,
  deletion or arbitrary model-selected handlers. The earlier AI task approval
  remains record-only; the separate local tool approval executes its exact
  authorized local action transactionally.
- Android production requests still use `OwnerIdentity.sign` and platform HTTPS.
  Test dependencies are per-call, with no global signing/TLS bypass. Disposable
  emulator tests use synthetic P-256 keys and a specific fixture CA, retain
  hostname verification, and talk to the real Python gateway. Only the OpenAI
  upstream is mocked. These tests do not certify a real owner's Keystore
  enrollment, physical device or live OpenAI account.

## Commands and results

```sh
.venv/bin/python -m unittest discover -s server/tests -v
.venv/bin/python -m scripts.verify_openai_acceptance --list-models --output NEW_EVIDENCE_PATH
git diff --check
```

The full Python run passed **152 tests**, with no failures or skips.
The read-only readiness command exited with `BLOCKED` before any remote request
because the key and allowlist are missing. `git diff --check` passed.

Android JVM results: **63 passed, 6 existing native/Keystore tests ignored**.
Lint and app/test APK compilation passed (0 lint errors, 31 warnings).
The configured HTTPS gateway emulator runner passed all **4** named tests with
no failures or skips and no external provider calls. The fresh full API 30
emulator rerun passed all **17** tests with no failures or skips: 13 native,
storage and owner-lock tests plus the 4 gateway integration cases. The 6 JVM
ignores correspond to native/Keystore behavior exercised on the real emulator.
Physical-device acceptance is **NOT_VERIFIED**.

The first emulator run exposed a 1.37-second client/server clock difference.
Android's new approval helper rejected a valid freshly created proposal despite
the signature protocol's existing 30-second tolerance. The helper now tolerates
that same creation-time skew and keeps strict expiry. An independent unit test
checks the accepted 30-second boundary, rejected 31-second boundary and expiry;
the corrected exact approval passes on the actual emulator.

## Reproduce the configured emulator fixture

Start the disposable local HTTPS fixture from this checkout:

```sh
.venv/bin/python -m scripts.android_gateway_fixture --ready-file NEW_PRIVATE_FIXTURE_JSON
```

The ready file contains generated **synthetic test** private keys and a fixture
certificate. Do not print or commit it. Read its port/arguments locally, use
`adb reverse tcp:PORT tcp:PORT`, and pass `instrumentation_args` as Android test
runner arguments for `OwnerGatewayIntegrationTest`. The fixture imports the
existing `server.gateway`; it implements no alternative gateway. All OpenAI
transport is replaced before accepting requests. Stop it after tests and retain
only its redacted `.evidence.json` counters.

The CI helper automates this lifecycle without printing fixture arguments:

```sh
.venv/bin/python -m scripts.run_android_gateway_acceptance --app-apk app/build/outputs/apk/debug/app-debug.apk --test-apk app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk --evidence-dir NEW_EVIDENCE_DIRECTORY
```

It requires exactly the four named tests to pass individually, rejects skipped
or zero-test runs, and removes its fixture/ADB forwarding afterward. The existing
Android CI emulator job now runs this helper with synthetic gateway dependencies
after its pre-existing instrumentation checks.

## External prerequisites and delivery

Environment configuration draft changes were saved for `api.github.com`,
`api.openai.com`, `developers.openai.com` and the personal proxy secret requirement
`KRAL_OPENAI_API_KEY`. Saving a draft does not apply the network policy, create a
key or publish the environment. The current running policy still blocks GitHub
REST with CONNECT 403, so PR creation is blocked until those settings are applied.

To finish stage C, use an existing authorized backend/key, set its approved model
allowlist, and run the read-only model catalog check. Then obtain explicit owner
approval for one synthetic request to an explicitly chosen allowlisted model.
Only after that approval may the following one-shot runner be used:

```sh
.venv/bin/python -m scripts.verify_openai_acceptance --live --approve-paid --model APPROVED_MODEL_ID --output NEW_LIVE_EVIDENCE_PATH
```

It makes at most one Responses call, uses a fixed synthetic input, caps output at
64 tokens, disables storage and never retries/falls back. The flag does not grant
permission itself. Evidence contains the actual returned model, response ID,
provider/client request IDs and an output hash, without a key or raw private
content. This command has **not** been run against a live provider in this task.
