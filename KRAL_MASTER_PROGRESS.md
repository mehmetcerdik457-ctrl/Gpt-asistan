# KRAL GENESIS 3.0 — MASTER PROGRESS
Last updated: 2026-11-04 (UTC)
Latest continuation: [1.0.9 gateway, memory deletion and encrypted backup](docs/KRAL_CONTINUATION_20261104.md).
Current continuation: `kral-genesis-parallel-20261104`, based on `f2fd46a3c6edfae4f37d2e78669418f00cb33d41`.
Current delivery and authorization: [parallel delivery](docs/KRAL_PARALLEL_DELIVERY_20261104.md).
The owner explicitly authorized verified main integration and APK delivery in this session.
The exact T01–T26 matrix has now been recovered from the authorized Drive document:
[source and verbatim criteria](docs/KRAL_ACCEPTANCE_CRITERIA_SOURCE_20261104.md).
Earlier missing-specification and PR-only continuation statements below are historical.
Current acceptance status is recorded in [the acceptance report](docs/KRAL_PARALLEL_ACCEPTANCE_20261104.md).

## Historical progress below

Repository: https://github.com/mehmetcerdik457-ctrl/Gpt-asistan
Active review: PR #79 (OPEN / DRAFT; NOT MERGED)
Working branch: audit/kral-api36-sqlcipher-integration-20261103
Verified HEAD: 7a53791d2845702a3b82ced311f2e91afa7ff6ce
Base branch: audit/kral-backup-privacy-20261103
Base SHA: b21eeaef5c42e64ec25433ac1fb8b11437691cf9
Main SHA observed: 5062b22ccfc11bdd10302bed75e5902deeb4ea4c

## 0. Continuation rules (owner instructions)
- Continue the existing KRAL GENESIS 3.0 / Gpt-asistan project; do not create a second app or a new project.
- Preserve existing Android sources, APK candidates, data-protection work, branch history, and artifacts.
- Do not merge PR #79 or change main without separate explicit authorization.
- Do not claim PASS without an exact commit-bound test result.
- The prior "22/26 PASS" claim is explicitly invalidated by the owner and MUST NOT be reused.
- Do not change the meaning of original acceptance criteria.
- Do not use paid APIs, create OAuth grants, rotate/enroll owner keys, change Play publication, delete user data, or perform irreversible operations without explicit approval.
- Continue updating this file before ending each work session.

## 1. Original specification status — BLOCKED / NOT RECOVERED
The requested original 28-section master roadmap and exact T01–T26 acceptance definitions were not found in the accessible current repository tree, PR #79, searched repository issues, current conversation files, or Library search results during this session.
The current PR branch contains docs/KRAL_SOL_WORKERS_ACCEPTANCE_20261101.md and docs/SQLCIPHER_DATA_PRESERVATION.md, but neither is the requested 28-section roadmap or T01–T26 acceptance matrix.
An earlier handoff issue records that the original KRAL Genesis 3.0 guide / acceptance matrix was not accessible to the prior executor either. Do not infer or recreate the original 26 tests from unrelated CI tests.
**Acceptance accounting rule:** T01–T26 = NOT VERIFIED (0/26 proven against original definitions) until the exact authoritative text is recovered. This is not a claim that all 26 failed; it means their original definitions are unavailable. The invalidated 22/26 assertion is not a baseline.

## 2. PR #79 inspection
PR: https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/79
- State: OPEN, DRAFT.
- Title: [DRAFT] KRAL API36 + SQLCipher: preserve chat, memory, worker and owner security.
- Head: audit/kral-api36-sqlcipher-integration-20261103 @ 7a53791d2845702a3b82ced311f2e91afa7ff6ce.
- Base: audit/kral-backup-privacy-20261103 @ b21eeaef5c42e64ec25433ac1fb8b11437691cf9.
- PR contains 18 changed files (Android SQLCipher integration, instrumentation, migration, workflow and data-preservation documentation).
- Main remains at 5062b22ccfc11bdd10302bed75e5902deeb4ea4c in the observed GitHub ref. PR #79 is not merged.
- SQLCipher KralStore and Android native instrumentation are part of the existing app, not a second application.
- Fail-closed migration behavior: existing plaintext SQLite DB with WAL/journal blocks migration; original files are not silently checkpointed or deleted. Plaintext legacy snapshot is retained pending an owner-approved retention/cleanup procedure.

## 3. Commit-bound CI/build evidence (HEAD 7a53791d)
### Python CI
- Run: https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41537007972
- Job: 125591300509; completed SUCCESS.
- Exact output: "Ran 53 tests in 15.451s" / "OK".
- Scope is the repository's Python suite and synthetic/local test contracts. It does not prove live provider access, a production HTTP 200, or the original T01–T26 acceptance suite.

### Android candidate build and emulator matrix
- Run: https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41537008081
- Workflow completed SUCCESS; source HEAD matches 7a53791d2845702a3b82ced311f2e91afa7ff6ce.
- API 30 emulator: 13/13 instrumentation tests PASS; APK install and launch PASS; owner-lock screen visible.
- API 36 emulator: 13/13 instrumentation tests PASS; APK install and launch PASS; owner-lock screen visible.
- These are 26 device-test executions across two emulator API levels, NOT the original T01–T26 tests. Do not conflate the counts.
- Emulator tests used x86_64 emulators. No physical phone test occurred.
- Emulator evidence JSON explicitly records: owner_authentication_attempted=false, persistence_on_emulator_tested=false, physical_phone_tested=false, live_model_tested=false.
- Instrumentation test themes include encrypted persistence/reopen, memory recall, Turkish-letter matching, migration preservation, WAL/journal and interrupted-staging fail-closed behavior, rollback/idempotency, invalid-role rejection, plaintext privacy, and owner-lock visibility.

### Android JVM/unit/lint
- Gradle log in artifact 13185405147 shows BUILD SUCCESSFUL and :app:testDebugUnitTest, :app:lintDebug, :app:assembleDebug, :app:assembleDebugAndroidTest, :app:bundleRelease.
- JUnit XML totals: 47 discovered test cases; 41 passed; 6 skipped/ignored; 0 failures; 0 errors. The 6 ignored tests are legacy Robolectric DB/lock tests because SQLCipher native DB behavior is tested under Android instrumentation. Do not count ignored tests as PASS.
- Two Kotlin Locale constructor deprecation warnings remain in KralStore.kt and MainActivity.kt. SQLCipher native library could not be stripped and was packaged as-is; this is a build note, not a failing test.

## 4. APK/AAB provenance
Candidate APK artifact:
- GitHub artifact ID: 13184342933
- Actions artifact: https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41537008081/artifacts/13184342933
- File: app-debug.apk
- Size: 13,526,465 bytes
- Package: com.example.gptasistan.genesis
- versionCode: 4
- versionName: 1.0.3-genesis-candidate
- minSdk 26; targetSdk 36; native ABIs arm64-v8a, armeabi-v7a, x86, x86_64.
- SHA-256: 60ce277d60a340113a9ae69ec868e6706371a95ac2c6d0d6f588e2db840b03be
- Signer certificate SHA-256: d5ddf2f047b0943b83bf16a07a3ca072940c6b5db7f6e98154fa21e255c83446
- apksigner verification: Verified; v2 scheme true; signer is Android Debug (RSA 2048); APK is debuggable. This is NOT a production/release signing identity.
- Exact source commit verified by build metadata: 7a53791d2845702a3b82ced311f2e91afa7ff6ce.
- The APK metadata file says emulator_tested=false; separate API30/API36 emulator evidence proves install/launch and 13 tests per API. Preserve this metadata inconsistency and rely on the separate commit-bound emulator evidence for those claims.

Unsigned AAB:
- Artifact ID: 13184578056
- Size: 8,073,232 bytes.
- SHA-256: a829992b0f60a4c51c168a5c90c53c39bbb3079fbff5809b342a085c6affa529
- Unsigned; not a Play-ready release.

Evidence artifacts:
- Build evidence artifact 13185405147 (gradle log, source.tar.gz, APK signature, metadata, unit-test XML, lint report).
- API30 emulator evidence artifact 13184008786.
- API36 emulator evidence artifact 13185261646.
- Unsigned AAB artifact 13184578056.
- Candidate APK artifact 13184342933.

## 5. Feature capability boundaries — current evidence only
Verified in current commit-bound test/build scope:
- Existing Android app compiles as one KRAL candidate.
- SQLCipher-backed local store and migration paths are covered by Android instrumentation.
- Chat/session persistence and local memory-recall behaviors are tested under emulator instrumentation.
- Owner lock gate visibility and signed-gateway/owner-worker Python contract tests exist.
- Python CI verifies dual-signature requirements, nonce/replay rejection, request bounds, provider allowlist behavior, local memory and idempotency behavior, and denial of unknown write tools using test doubles/synthetic data.

Not verified / still open:
- Actual owner/device P-256 enrollment and successful authenticated owner session.
- Live OpenAI or other model-provider request, quota, model availability, or actual generated answer.
- Google AI Studio project/source export or integration; no connected AI Studio/Drive source access was available in this execution. No imported AI Studio code is claimed.
- Full supported-world-language coverage, speech input/output, files/document processing, automatic model selection against live providers, real independently executing specialist agents, connector lifecycle, and permissioned phone actions.
- Real device upgrade/signature compatibility and existing user-data migration on a physical handset.
- Approved WAL/journal recovery/checkpoint and plaintext-legacy retention/cleanup procedure.
- Stable owner-controlled release signing, Play Console internal testing/publication, and production deployment.
- Ten independent real attack/test methods per feature; this has not been performed.

## 6. Security / release blockers
1. Debug signer is not a stable owner-controlled release signer. Do not uninstall an existing production APK or attempt in-place update with this candidate; signature mismatch can block upgrade and uninstall may erase local data.
2. Existing plaintext DB WAL/journal prevents migration by design. No automated data deletion/checkpoint is allowed.
3. Owner P-256 enrollment and device binding remain untested against real owner keys.
4. Live provider tests require an owner-authorized provider configuration/quota; no API secret values are to be exposed.
5. AI Studio work must be obtained through an authorized export or connected source; no assumptions about its contents.
6. Original 28-section roadmap and T01–T26 exact text must be recovered before original acceptance can be evaluated.

## 7. Completion / confidence accounting
- Overall completion percentage: NOT MEASURABLE. The authoritative 28-section scope and T01–T26 definitions are missing; no percentage is to be invented.
- Original T01–T26: 0/26 verified against original acceptance text (definitions unavailable; not counted as failed).
- Current Python CI: 53/53 PASS at exact HEAD.
- Current Android instrumentation: 13/13 PASS on API30 and 13/13 PASS on API36 (26 emulator executions, not original T-tests).
- Android JVM tests: 41 PASS, 6 SKIPPED/IGNORED, 0 FAIL, 0 ERROR.
- Feature failure rate: NOT MEASURABLE across all product features because no complete feature-level test denominator / ten-method matrix exists.
- Physical device tests: 0.
- Live model tests: 0.
- Production release signature: NOT PRESENT.
- Confidence is high for the cited GitHub Actions outcomes and artifact hashes; low/unavailable for any untested live/physical/production behavior.

## 8. Next execution sequence (continue here; no restart)
1. Recover the authoritative 28-section roadmap and exact T01–T26 acceptance wording from the owner's original source/Google AI Studio export or an authorized prior file. Do not substitute a reconstructed checklist.
2. Import/review the actual Google AI Studio source as a patch against this same Android app; preserve package/application identity and avoid a second app. No AI Studio code was available during this session.
3. Map each exact T01–T26 criterion to existing source/tests and evidence. Keep unknown criteria BLOCKED, not PASS.
4. Continue PR #79 branch only. Do not merge to main.
5. Fix verified defects only, add regression tests, and rerun exact commit-bound CI/emulator workflows after any code change.
6. Implement the next open security gates: owner-authorized P-256 enrollment test plan, stable release signing decision, data-preserving physical upgrade/migration plan, and approved WAL/plaintext legacy handling. Ask owner before any critical key enrollment, release signing, publication, paid API, or destructive migration.
7. For each future session, append timestamped evidence and update this file.

## 9. Current stage decision
**Stage result: BUILD EVIDENCE VERIFIED; PRODUCT / ORIGINAL ACCEPTANCE NOT COMPLETE.**
PR #79 remains a draft integration review. No main merge, production release, physical device test, live model test, or original T01–T26 acceptance is claimed.


## 11. OpenAI Responses task-runtime continuation — 2026-11-03 12:00 Türkiye time
**This section supersedes the earlier PR #79-only continuation instruction in Section 8.4 for the separate OpenAI task-runtime work.** The user's 2026-11-03 instruction explicitly directs this integration through the existing PR #82 → #83 → #84 chain and its PR #85 continuation. PR #79 remains preserved and untouched by this work.

- Active repository: `mehmetcerdik457-ctrl/Gpt-asistan`.
- Active PR: [#85 — KRAL bounded Responses task lifecycle and expert routing](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/85), OPEN / DRAFT; no merge.
- Active head branch: `integration/kral-genesis-task-runtime-20261103`.
- Latest code commit at this progress update: `b7b4541060cdf54f0918b2a10a8cff0214c689c9` (verify full SHA from GitHub before reuse).
- PR #85 base is `audit/kral-agent-roles-recovery-20261103` at PR #84 head `74ff9ef3930b0bc3a0fbbccb4bfe3dd91a5a00f6`. PR #82/#83/#84 chain was preserved; no base/main branch mutation.
- Preserved architecture: server-only OpenAI Responses API through the existing owner gateway; existing dual P-256 owner/device signatures and nonce checks; `store=false`; existing model allowlist and 4-slot shared execution semaphore; 12 expert profiles are prompt-routing profiles, not autonomous GitHub/Copilot tool permissions.
- Implemented in this continuation:
  1. `server/gateway.py`: added `reply_with_metadata()`; attaches non-sensitive task correlation metadata and `X-Client-Request-Id`; captures Responses `id` and response `x-request-id`; safely parses bounded error metadata and numeric `Retry-After`; distinguishes temporary 429/500/503 codes from billing/quota 429s. Provider error bodies and API keys are not returned.
  2. `server/task_runtime.py`: additive SQLite columns for client request ID, Responses ID, provider request ID, HTTP/error metadata and retry hints; passes task ID/expert/runtime metadata; records provenance on success/failure; continues to use the shared four-slot execution semaphore.
  3. `server/tests/test_gateway.py`: synthetic tests for metadata/request-ID round trip, prompt exclusion from metadata, invalid metadata rejection, and 429/500/503 retryability vs quota/spend errors.
  4. `server/tests/test_task_runtime.py`: synthetic tests for task/response/request provenance, retry hints and no automatic replay of POST requests.
  5. `app/src/main/java/com/example/gptasistan/OwnerIdentity.kt`: allowlisted signed task, status, cancel and approve routes in the existing P-256 canonical request envelope.
  6. `app/src/main/java/com/example/gptasistan/OwnerGateway.kt`: Android task submit/status/cancel/approve client methods; typed task parser validates task IDs, request/result hashes, provider IDs, HTTP/retry fields, and insists on zero tools/external actions.
  7. `app/src/test/java/com/example/gptasistan/OwnerGatewayTest.kt`: parser tampering tests and signed task-route canonicalization tests.
  8. `app/src/main/java/com/example/gptasistan/MainActivity.kt`: adds an explicit “Uzman AI görevi” UI, 12-role selector, task submission/status refresh/cancel/approval-record flow. User action is required to submit. UI explains possible API usage; no live request was made by this coding session.
- Safety boundaries remain: `tools=[]`; no shell, network, GitHub writes, autonomous external actions or model tool calls. Approval is recorded as `approved_not_executed` and does not execute anything. Cancel on a running synchronous request only sets a cancel flag and discards the eventual result; it does NOT cancel the upstream OpenAI HTTP request. No automatic retry is performed; retryable status and Retry-After are recorded only, avoiding an unapproved duplicate paid POST. Billing/spend/quota errors are not marked retryable.
- Official OpenAI references checked: Responses create returns a Response ID; API overview documents `x-request-id` and caller-supplied `X-Client-Request-Id`; rate-limit guide distinguishes temporary `429 slow_down` and `503 server_is_overloaded` from spend/quota failures and directs callers to honor `Retry-After`. Background cancellation applies only to Responses created with `background=true`; this implementation remains synchronous with `store=false` and does not claim remote cancellation.
- **Verified CI evidence before the final Android UI-only commits:** Python CI run [41607819361](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41607819361) passed on commit `a8183b7505e334899b9f22cc197e784e2be189d3`; log reports **95 tests, OK**. This commit includes backend provenance/retry code and Android signed task-client/parser/test changes, but predates the MainActivity UI addition.
- **Final code commit `b7b454...` CI is not yet verified:** latest CI and Android candidate runs were queued at time of writing: [CI 41607931889](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41607931889) and [Android 41607931980](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41607931980). Do not mark final UI/build PASS until these runs complete successfully.
- No live OpenAI key/configuration/entitlement was inspected or verified. No paid API request was made. No secret values read or revealed. No OAuth, new key, spend, production deployment, APK publication, stable signing, main merge, physical phone test, or Google AI Studio source import occurred.
- Next step: poll the exact final-head CI and Android candidate runs; inspect failure logs and fix only evidenced defects. Then run the Android task endpoints end-to-end against a synthetic gateway fixture (never a paid provider), verify owner-signature denial/replay protection on task/status/cancel/approve routes, and update this file again. Keep PR #85 draft and do not merge.


## 12. Final continuation correction and latest evidence — 2026-11-03 12:15 Türkiye time
This section supersedes any stale statements in Section 11 about a newly added MainActivity screen or the earlier pre-final commit.

- **No new Android screen or MainActivity UI is part of this task.** The temporary MainActivity UI experiment was reverted to the existing Android screen from commit `a8183b7505e334899b9f22cc197e784e2be189d3`, honoring the existing no-new-UI boundary. Android integration is through the existing `OwnerGateway` contract only.
- The Android client still has signed methods for `submitTask`, `taskStatus`, `cancelTask`, and `approveTask`, all using the existing dual-P-256 canonical envelope. `OwnerGateway.parseTask` validates the task ID, request/result digests, Responses ID, provider request ID, client request ID (must equal task ID), HTTP/error fields, retry fields, and zero tool/external-action counts.
- Existing chat now propagates `response_id`, `provider_request_id`, and `client_request_id` from the server into `OwnerGateway.Reply` and `ChatSession.State`. Typed Android `GatewayFailure` preserves only sanitized error code, provider request ID/status/code, retryable flag, and bounded Retry-After. Error bodies are read with a 16 KiB ceiling and are never exposed in exception messages or chat history.
- The 12 expert identifiers remain constrained prompt-routing profiles; they are NOT 12 independent hosted agents or separate autonomous Copilot sessions. The task manager has 50 logical active slots and a four-worker execution pool sharing the four-slot provider semaphore.
- Approval remains deliberately non-executing: `awaiting_approval` → `approved_not_executed`. Tools remain empty; no shell, network, GitHub write, or external action can be run by a model.
- Cancellation remains local-only for the current synchronous `store=false` request: queued work can be cancelled; a running task is flagged and its eventual result discarded. It does not terminate the upstream synchronous HTTP request. OpenAI documents that the remote cancel endpoint works only for Responses created with `background=true`; background mode temporarily stores response data for roughly 10 minutes even with `store=false`. I have NOT enabled that retention tradeoff. Remote cancellation requires explicit owner approval of that behavior.
- Automatic retries remain disabled. Synthetic tests distinguish temporary 429 `slow_down`/`rate_limit_exceeded`, 500 `server_error`, and 503 `server_is_overloaded` from billing/quota/spend 429s; retryability and numeric Retry-After are recorded only. No POST is replayed automatically.
- Latest code head: `4759b046130a7e1eed5caff0093e347c27e673c9`.
- Latest Python CI: [run 41608870212](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41608870212), SUCCESS, **101 tests / 101 passed**, log: `Ran 101 tests in 18.839s` / `OK`. This run is on the current code head.
- Latest Android candidate build for this same head: [run 41608870066](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41608870066), QUEUED at this update. An earlier Android build [run 41608174629](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41608174629) completed the Gradle build successfully on an earlier task-client commit, but its emulator jobs were still queued. Do not claim the current-head Android build or emulator tests PASS until run 41608870066 completes.
- PR #85 remains OPEN / DRAFT and unmerged. Base branch remains `audit/kral-agent-roles-recovery-20261103`; `main` remains at `5062b22ccfc11bdd10302bed75e5902deeb4ea4c`. PR #79 was not changed by this integration. No APK artifact from current head is yet verified.
- No live `GET /v1/models` was run; no API key, secret value, project billing state, or model entitlement was inspected; no live Responses request or paid call was made. No new OAuth, key, spend, deployment, release signing, publication, or merge occurred.
- The exact Google Drive custom guide could not be retrieved in this session because the connected Drive source was unavailable. The repository's preserved [`docs/KRAL_OPENAI_MODEL_ACCESS.md`](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/integration/kral-genesis-task-runtime-20261103/docs/KRAL_OPENAI_MODEL_ACCESS.md) was used as the in-repo guide summary; it explicitly treats the `runKralAiTask` JavaScript example as an interface illustration, not authorization for a second provider integration.
- Next step: wait for current-head Android build run 41608870066, inspect its compile/test/emulator logs, fix only evidenced failures, and then verify the generated artifact's source SHA, package/version, size, and signing identity. Keep PR #85 draft and do not merge.



## 13. OpenAI integration verification completed — 2026-11-03
This section supersedes Section 12's queued Android status.

- Verified PR #85 head: `a429e4893ed373b52c64273cb96c9a93dd6126f9`, OPEN / DRAFT, unmerged. Base remains `audit/kral-agent-roles-recovery-20261103`.
- Python CI [41609232371](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41609232371): SUCCESS; archived test log reports **101 tests, 18.254s, OK**.
- Android candidate build [41609232198](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41609232198): SUCCESS. Gradle build, unit tests, lint, APK/AAB packaging and APK signature/hash checks completed successfully.
- Android unit test XML: 59 tests total, 53 passed, 6 skipped, 0 failures, 0 errors. Skips are explicitly reported; they are not counted as passes.
- Emulator API 30 and API 36: each installed the same APK, launched MainActivity, confirmed owner lock screen visible, and passed 13 instrumentation tests. The instrumentation did **not** attempt owner authentication, persistent-data migration, or live model access. No physical phone test occurred.
- Candidate APK artifact [13218332391](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41609232198/artifacts/13218332391), ZIP SHA-256 `d3b30c69cd8a3255f6af9724dfbd8b3c8229c30c82c017862b8fa651beb039da`. Extracted APK: `app-debug.apk`, 13,542,849 bytes, SHA-256 `f8043fa8ed8d154a63b5f2db889cce6bb6a81563002738557a8784cc843cb934`.
- APK metadata verifies exact source commit `a429e4893ed373b52c64273cb96c9a93dd6126f9`, package `com.example.gptasistan.genesis`, versionCode 4, versionName `1.0.3-genesis-candidate`, minSdk 26, targetSdk 36, INTERNET plus Android dynamic receiver permission only. Signature verifies with Android Debug certificate SHA-256 `7775717aedd0d026f89493aa66d7dff61d5d357d603315b6ed282d9857c29858`; APK is debuggable and is **not** signed with a verified Play/release key.
- Unsigned AAB artifact [13217888328](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41609232198/artifacts/13217888328) is explicitly NOT Play-ready.
- Existing synthetic Gateway tests cover signed task submit/status/cancel/approval, owner/device signatures, nonce replay rejection, task provenance, response/request ID propagation, retry classification and no automatic POST replay. Android parser tests validate response IDs and task result fields. No live OpenAI request, API-key inspection, model entitlement check, paid usage, production deploy, release signing, Play upload, or merge occurred.
- Remaining gates: owner-authenticated Android physical-device E2E; real server-side GET /v1/models using an already-authorized server configuration (not available from this GitHub connection); separately approved billable Responses call; production package/signer/version compatibility; and release/Play acceptance.
