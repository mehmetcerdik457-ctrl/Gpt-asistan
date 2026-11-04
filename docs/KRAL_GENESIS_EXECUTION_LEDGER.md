# KRAL Genesis execution ledger

Updated: 2026-11-04 UTC. This is a continuation of
`evidence/genesis-v128/`; its 28-section inventory and T01-T26 matrix remain
the starting point, not proof of acceptance. The original roadmap was not
retrieved in this session; its detailed requirements are not yet mapped.

## Evidence and boundaries

- Baseline: `532918be0dfcaa25ce8c3302a299b3d562d985b2`, based on
  `5c365322ca1722d0e837a2785d4fc4401cea56b8`; it includes the 1.0.6
  candidate `b87b1c538be5c777b52ac5e64db2d384e3e18860`. The protected
  1.0.5 source is `276f84109cb32826416d63b8b4d18bb702190f3c`.
- Prior Android CI for `5c36532`, not this change:
  [run 41753708922](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41753708922).
- For source `4495de597954a354f53283d7ef5a3a37522c1488`, the Python
  [CI run 41847326490](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41847326490)
  succeeded, as did Android build and API 30/36 emulator jobs in
  [run 41847326360](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41847326360).
  Android JVM tests: 75 passed, 6 skipped, 0 failed; lint passed with warnings.
  The artifact was downloaded and its recorded SHA-256 verified locally.
- That CI candidate is `com.example.gptasistan.genesis`, versionCode 7,
  versionName `1.0.6-genesis-candidate`, APK SHA-256
  `41ed1881ce788599d15aebc2148612ceff9cbaeeaa522eda4564f71a591e48b3`,
  debug signer SHA-256
  `6fd07125d5d188757967b5ba4c849a98daf07f79c063bce019ce11d58780b9eb`.
  The pinned owner signer is different; owner signing and an in-place upgrade
  were not verified. Do not install over an existing app or treat it as a
  release. Emulator results are separate from physical-device acceptance.
- GitHub account authentication is not proof of KRAL owner/device identity.
  No live provider, physical device, installed signer, upgrade, Drive delivery
  or public release was verified here.
- Local unchanged-baseline `./gradlew :app:assembleDebug --no-daemon`
  failed with Java 27; Android SDK is not configured. Do not label an APK or
  data-preserving update ready.
- Local Python baseline: `python3 -m unittest server.tests.test_android_owner_signing
  server.tests.test_android_upgrade_gate server.tests.test_task_runtime
  server.tests.test_idempotency`: 41 passed. After the change, the same
  command passed 42. A full initial run failed with five missing-dependency
  errors; after installing the existing pinned requirements into an isolated
  virtual environment, `python -m unittest discover -s server/tests` passed
  122 tests. These are local/synthetic tests, not device or provider evidence.

## Queue and dependencies

Each row records requirement → task → source → implementation → test →
evidence → status → next. `TESTED_MOCK_ONLY` denotes the available synthetic
test coverage, not acceptance of the complete requirement.

| Requirement | Task | Source | Implementation | Test and evidence | Status | Next |
|---|---|---|---|---|---|---|
| 11, 16, T17 | RUNTIME-RESTART-OUTCOME | `server/task_runtime.py` | Do not let a late provider outcome replace a non-running task's recorded restart failure. | `server/tests/test_task_runtime.py`: late success and failure with synthetic provider; full local suite above. | TESTED_MOCK_ONLY | Design durable checkpoints, cross-process ownership and safe resume separately; do not automatically repeat an uncertain external action. |
| 11, 16, T17 | RUNTIME-RESUME | `server/task_runtime.py`, `server/idempotency.py` | Not implemented. Existing restart marks queued/running work failed. | No safe-resume or external-effect test. | NOT_STARTED | Define durable encrypted input, leases, replay policy and idempotency before implementation; depends on RUNTIME-RESTART-OUTCOME and security review. |
| 8, 18, T26 | SIGNER-DEVICE | `scripts/check_android_upgrade.py`, `scripts/android_owner_signing.py` | Existing offline signature gate; no changes to signing identity. | Synthetic signing/upgrade tests only; installed APK unavailable. | BLOCKED | Inspect an authorized physical device and compare the actual installed signer and candidate without uninstalling. |
| 2, 21, 24, 27 | ROADMAP-MAP | Original Google document linked in the request; `evidence/genesis-v128/KRAL_TASK_LEDGER.json` | Existing partial section inventory. | Original document retrieval failed DNS in this session. | BLOCKED | Obtain authorized access to the original document; map each criterion without guessing. |
| 4, 5, T04 | DRIVE-INVENTORY | ANNEM folder linked in the request | Not performed. | No authorized Drive connector verified. | BLOCKED | Obtain authorized read access; inventory metadata only before selecting relevant documents. |
| 6, T08 | LIVE-MODELS | `server/gateway.py` | Existing adapter only. | No live provider request was authorized or performed. | BLOCKED | Verify provider authorization and costs separately before any live request. |
| 19, 20 | DURABLE-EXECUTOR | Existing evidence records and GitHub workflows | No autonomous executor was installed. | No unattended continuation or stop control verified. | NOT_STARTED | Design bounded, approval-aware durable execution without unapproved costs or external effects. |

Rollback of RUNTIME-RESTART-OUTCOME: revert its commit on the development
branch; do not reset user data or alter signing identities. The implementation
does not provide checkpoint/resume, exactly-once external actions or a release.

## Android build and upgrade follow-up

- An isolated Temurin 17.0.21 installation runs the Gradle 8.13 wrapper on
  Java 17. The local `:app:assembleDebug` still fails to resolve Android Gradle
  Plugin 8.13.2: this environment could not resolve `dl.google.com`, and it has
  no Android SDK configured. The existing successful GitHub-hosted build above
  is separate evidence, not proof of a successful local build.
- The candidate and instrumentation APKs from run 41847326360 matched their
  published SHA-256 files. The separately downloaded API 30 and API 36
  instrumentation summaries each record 16 passed tests for the same source
  and APK; neither claims a physical phone test.
- `python3 -m unittest server.tests.test_android_owner_signing
  server.tests.test_android_upgrade_gate server.tests.test_android_delivery_evidence
  server.tests.test_android_instrumentation_evidence` passed 37 local tests.
  These are synthetic gate and evidence tests, not an actual owner signing or
  installed-APK upgrade.
- The 41847326360 signing report says `DEBUG_ONLY_UNTRUSTED_EVENT` and
  `previous_install_upgrade_verified: false`. Its signing certificate differs
  from the historical owner pin. The trusted signing branch named in the
  current workflow no longer exists, and the Actions secrets metadata API
  returned HTTP 403. Do not weaken the signing event boundary or assume that
  a different signer can update the installed application.
- The original roadmap file, actual installed APK identity, owner signing key
  availability, and physical-device upgrade evidence remain unavailable.
  T01–T26 and a safe final APK remain unaccepted; do not uninstall or reset
  the existing application to bypass a signature mismatch.
