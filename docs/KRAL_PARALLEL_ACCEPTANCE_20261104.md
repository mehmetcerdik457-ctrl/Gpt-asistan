# KRAL parallel acceptance assessment — 2026-11-04

The exact original T01–T26 pass conditions were recovered through the connected
Google Drive reader. The previous missing-matrix blocker is resolved. See
[the verbatim source excerpt](KRAL_ACCEPTANCE_CRITERIA_SOURCE_20261104.md) and
[the machine-readable assessment](../evidence/parallel-20261104/KRAL_ACCEPTANCE_RESULTS.json).
The source was read only; no original Drive document was edited.

This assessment covers the integration working tree based on
`f2fd46a3c6edfae4f37d2e78669418f00cb33d41`. Local checks below are not bound
to a final commit. The coordinator's delivery record supplies the final source
SHA, CI conclusions, artifacts and hashes after integration.

Only T04 is currently verified against its original wording: an authorized
source file was found and its actual Drive ID returned. This is source access
from the execution environment. It does not establish Drive integration inside
the Android app. PARTIAL means relevant code or narrower tests exist, while
one or more original pass conditions remain unproven; it is not a PASS.

## Current module evidence

| Module | Implemented or corrected | Verification and remaining limits |
|---|---|---|
| Android UI/draft/voice | OTP unlock additionally requires the device credential; separate OTP server address; stale callbacks rejected; sensitive dialogs dismissed on background; speech draft survives Activity recreation. | Four Robolectric regressions added by UI owner. Local Gradle startup could not download services.gradle.org; exact-head CI is required. Real speech/credential/device E2E remains untested. |
| OTP/SMTP backend | Secure TLS SMTP adapter and fixed-owner OTP endpoints; stable server secret required for real SMTP, failed-delivery rate limiting preserved, exact-expiry checks corrected, implicit TLS selection fixed. | Backend owner reports 140 tests passed in 20.276s, including 16 OTP tests and current evidence-validator tests. Isolated fixtures; no live SMTP/provider call. |
| Release/universal signing | Gradle/signing and workflow owners are integrating pinned owner signing and universal APK/AAB evidence. | Final signer result depends on configured owner keystore and pin; a debug certificate must not be described as owner release signing. |
| Test evidence | JUnit results now require a unique identity for every executed testcase and exact agreement between declared counts and testcase outcomes. | 11 evidence regression tests pass. Truncated XML, duplicate reports, negative counts and hidden failures now fail closed. |
| CI/CD | Baseline Android run [41866716917](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41866716917) built source f2fd46a; baseline Python run [41866716594](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41866716594) succeeded with 132 tests in 21.719s. | Baseline JVM: 79 passed, 6 skipped, no failures; lint passed with warnings. API 30 and 36 logs each report 16 instrumentation tests passed and install/launch success; final evidence-upload conclusion was pending at assessment. Final integration CI and artifacts require separate exact-source evidence. |

## Original acceptance mapping

| ID | Original test | Assessment | Evidence or missing execution |
|---|---|---|---|
| T01 | Orijinal koruma | PARTIAL | Original source history retained; no complete before/after inventory of every original APK/Drive resource. |
| T02 | APK teknik inceleme | PARTIAL | Baseline f2fd46a Android Actions metadata identifies package, certificate, version, permissions, ABIs and source; final integrated APK inspection pending. |
| T03 | GitHub erişim/derleme | PARTIAL | Baseline f2fd46a Android run 41866716917 built APK; final integrated commit/build pending. |
| T04 | Google Drive erişim | PASS | Connected Drive search/fetch found authorized KRAL GENESIS document and returned actual file ID 1dTkLQwJzRimb3b0m-H7RtUSSo48E_pLYVeJSYnxLd2M; proves executor source access, not Android Drive integration. |
| T05 | Eski bot/motor | NOT_TESTED | No legacy motor source and real function execution verified in this operation. |
| T06 | Kaynaktan yeni yetenek | NOT_TESTED | No new externally sourced APK/SDK/model capability acquired and executed. |
| T07 | Yeteneği yeniden kullanma | NOT_TESTED | No independent later task demonstrated autonomous reuse of an acquired capability. |
| T08 | Model seçimi/alternatif | PARTIAL | Provider allowlist and error classification have synthetic coverage; no real two-tool fallback. |
| T09 | Kalıcı hafıza | PARTIAL | Android SQLCipher close/reopen and recall instrumentation exists; final emulator rerun and deletion acceptance missing. |
| T10 | Ses | PARTIAL | SpeechDraft logic and TTS/STT UI exist; no real voice-to-authorized-tool-to-spoken-response execution. |
| T11 | Sahip doğrulama | PARTIAL | Dual-signature, replay denial, OTP and local credential gates have isolated tests; real spoofed voice/session critical-command test missing. |
| T12 | Android eylem | NOT_TESTED | No physical Android device attached or multi-step device action executed. |
| T13 | Google görevi | NOT_TESTED | Read-only Google source recovery succeeded; no new authorized Google workflow output delivered by KRAL. |
| T14 | Video üretimi | NOT_TESTED | No video generation and format/playability verification performed. |
| T15 | Dış yayın | NOT_TESTED | No authorized publishing workflow or platform output ID/idempotency verified. |
| T16 | Kod/APK üretimi | PARTIAL | Code/build evidence exists; criterion additionally requires APK operating on a real device. |
| T17 | Kesinti/tekrar | PARTIAL | Restart/cancel/idempotency tests use isolated provider doubles; durable successful task resume is not implemented. |
| T18 | Süreklilik/bildirim | NOT_TESTED | No product background-work/notification runtime acceptance performed. |
| T19 | Offline/online | PARTIAL | Local memory/draft code exists; remote wait/recovery with a real offline-online transition not tested. |
| T20 | Prompt injection | PARTIAL | Unknown tool fields/actions rejected in isolated gateway tests; no full untrusted file/tool-output injection scenario executed. |
| T21 | Sır/erişim savunması | PARTIAL | Secret-redaction and authorization attacks covered by isolated gateway tests; no complete product critical-secret attack matrix. |
| T22 | Geliştirme döngüsü | PARTIAL | Evidence validator defect reproduced and corrected with 11 passing regression tests; final committed rollback and exact-head CI pending. |
| T23 | Geri yükleme | NOT_TESTED | No real encrypted backup restored into a separate test installation. |
| T24 | Kontrollü kopya | NOT_TESTED | No authorized second device/environment installation acceptance performed. |
| T25 | Kullanım kolaylığı | PARTIAL | Existing Android UI and drafts integrated; natural-command file/link-to-workflow usability acceptance unexecuted. |
| T26 | Tam teslim | PARTIAL | Baseline CI/candidate artifacts exist; final signed integrated APK, verified Drive upload/redownload hash and device compatibility pending. |


## Evidence defect closed

Before this change, `android_delivery_evidence.summarize` accepted XML declaring
five tests but containing only two skipped testcase nodes and reported three
passes. It also trusted a zero-failure attribute even if testcase failure nodes
were present. The verifier now cross-checks every count against actual nodes,
rejects repeated/missing test identities and invalid outcomes, and keeps real
skips separate. Existing instrumentation verification continues to require
individual Android passes covering every skipped JVM test.

Executed command:

```sh
python3 -m unittest server.tests.test_android_delivery_evidence server.tests.test_android_instrumentation_evidence -v
```

Result: **11 tests, OK**, synthetic evidence-validation fixtures. The backend
owner's later full run included this change: **140 tests, OK**. Final integrated
counts may grow as other owners finish their tests.

## Remaining execution requirements

A physical handset/installed package is unavailable here, so actual-device
operation, installed signer compatibility, data-preserving in-place upgrade,
voice-to-tool operation, second installation and backup restore remain unproven.
No live SMTP or provider configuration was supplied in this environment. Source
recovery and passing isolated tests do not prove those service operations.
Drive source read access is now verified; final upload and re-download hash
verification are separate operations required by T26.

The original acceptance matrix also includes legacy capability acquisition,
autonomous later reuse, real fallback, media production, external publishing,
background execution and complete restore. Those are product capabilities and
runtime tests beyond a successful APK build; they cannot be replaced by a
count of Python/JVM/emulator test executions.

