# MEHMET Owner Companion — controlled Android development

**This repository is not the full PROJECT OMEGA.** The Android Owner and Bridge apps, the CİHAT worker, the public MEHMET AI backend, and local OMEGA D1–D5 archives are different sources with different identities and acceptance gates.

## Modules

| Location | Role | Security boundary |
|---|---|---|
| `app/` | Android Owner Companion 1.5.4 (versionCode 12) | Biometric/device-credential Owner authentication, Android Keystore, request policy |
| `bridge/` | Separate signed-by-owner Bridge 1.2.1 (versionCode 4) | Signature-constrained IPC and accessibility postconditions |
| `control-plane/` | Owner orchestration experiments | Not a production identity provider |
| `kral/` | Separate local workstream | Not automatically integrated |
| `tools/` | Test and verification scripts | CI evidence is not physical-device acceptance |
| `docs/` | Integration and audit specifications | Draft unless a gate is explicitly accepted |

CİHAT AI / Chatbot AI 3.2.1 is the separately distributed worker `com.codespaceapps.aichat` and is **not** this Owner APK. Its vendor source code is not incorporated into this repository.

Public MEHMET AI backend: [benim-uygulamam](https://github.com/mehmetcerdik457-ctrl/benim-uygulamam). Its existing `backend/server.py` is a Python `http.server` implementation; **not** proof of an integrated FastAPI/PostgreSQL deployment. Current Owner directly calls the canonical OpenAI HTTPS endpoint, not that backend. The proposed contract is [docs/OMEGA_OWNER_BACKEND_CONTRACT_20261019.md](docs/OMEGA_OWNER_BACKEND_CONTRACT_20261019.md).

## Source + release separation

Owner hotfix: [draft PR #32](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/32). The network/auth correction is [draft PR #36](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/36), **stacked** on #32. Do not merge to `main` without independent review and owner approval.

- `gradle :app:testDebugUnitTest` — Android unit tests with Gradle/Android SDK.
- `gradle :app:assembleRelease :bridge:assembleRelease` — **unsigned** release artifacts. They are not install-ready production APKs.
- `python3 -m unittest discover -s tools -p 'test_owner_provider_gate.py' -v` — 5 static security-invariant tests.
- `javac -d /tmp/omega-provider-tests app/src/main/java/com/mehmetcerdik/ownerai/ProviderNetworkErrors.java tools/ProviderNetworkErrorsTest.java && java -cp /tmp/omega-provider-tests com.mehmetcerdik.ownerai.ProviderNetworkErrorsTest` — 6 direct exception-classification assertions.
- GitHub workflows `android.yml` and `phone-agent-emulator.yml` produce build/emulator evidence, but do not certify the owner's physical phone.

Never embed, commit, paste, or export a live provider key or signing material. The `.env.example` values are **blank placeholders** only. Store active credentials in an authorized local/provider secret store; Android Keystore authentication must remain enforced.

## Device errors and observed meaning

- `FRESH_OWNER_AUTH_REQUIRED_FOR_PROVIDER_SECRET`: the provider AES-GCM key requires fresh owner authentication (Keystore validity 30 seconds), independent of the 2-minute session. PR #36 prompts fresh authorization before model and OCR calls; a real Keystore/device test is still required.
- `PROVIDER_DNS_UNAVAILABLE`: Android could not resolve a provider host. It does **not** prove an invalid API key, empty account quota, or service failure.
- `PROVIDER_NETWORK_TIMEOUT`, `PROVIDER_CONNECT_FAILED`, `PROVIDER_TLS_FAILURE`: sanitized transport errors; exception strings must not appear in replies or logs.
- `secret_configured=true`, `bridge_verified=true`, `audit_chain_valid=true` attest to **separate local conditions**, not successful live model inference.

## Acceptance limits

Code built + emulator tested is **not** production signed release, Android physical-device acceptance, live provider response, or end-to-end OMEGA acceptance. Do not weaken owner verification, modify the distributed CİHAT app, overwrite signed original APKs, or grant higher privileges to make tests pass.
