# ORBA — unsigned release AAB structural preflight (DRAFT)

This extends the existing Play source/debug APK gate, without invoking
Google Play Console, authenticating a merchant or producing a signed release.

## Offline acceptance
- GitHub Actions runs all previous Python/Android tests and Android lint.
- `:app:assembleDebug` remains independently verified using `aapt` and
  `apksigner` to check compiled debug APK identity and signature.
- `:app:bundleRelease` builds the RELEASE VARIANT, without installing an
  upload signing key. CI checks the generated `app-release.aab` ZIP layout,
  `BundleConfig.pb`, `base/manifest/AndroidManifest.xml`,
  `base/resources.pb`, at least one `base/dex/classes*.dex`, CRC,
  duplicate entries, path traversal, expansion caps and disallowed
  JAR signature markers. The bundle is not presumed signed just because
  Gradle succeeded.
- CI SHA-256 fingerprints the AAB and publishes a distinct short-lived
  **`orba-UNSIGNED-aab-preflight-NOT-FOR-PLAY`** artifact.
- Every successful static acceptance prints `production=HOLD`,
  `release_upload_ready=false`, `play_console_signing=NOT_VERIFIED`.
- The binary protobuf AAB manifest package is NOT decoded by this scanner;
  the source package and independently tested debug APK are checked by
  the existing guard. AAB bundletool manifest inspection is a separate
  acceptance criterion, not falsely counted here.

## Production gates that remain MISSING

1. Independently identify the real ORBA Play Console package; it may differ
   from development `com.example.gptasistan.genesis` and must not
   be silently rewritten if customers have installed a signed app.
2. Independently verify Play Console subscriptions, base plans/offer IDs,
   license testers, developer identity and subscription visibility.
3. Obtain and securely configure the authorized upload signing key
   outside GitHub; compare its X.509 fingerprint with the Play Console
   upload certificate. Never create a replacement key for an existing
   published app without owner review.
4. Generate a signed AAB, verify signature using `jarsigner` and inspect
   package/version through the official `bundletool`, then test on
   Play internal track and Android device/emulator compatibility matrix.
5. Conduct the live license tester purchase, verify, ACK, restore,
   cancellation/grace/hold/refund/expiry flows and OIDC RTDN webhook.
6. Explicit owner approval before merge, deployment, any merchant payment
   or real publication.

The unsigned AAB is **NOT** installable directly, not an upload candidate,
and not evidence of production entitlement or live payment.

Official guidance:
https://developer.android.com/build/build-for-release
https://developer.android.com/build/building-cmdline
https://developer.android.com/studio/publish/app-signing


## 14 Nov 2026 — official checksum-pinned bundletool decoded AAB manifest

Draft PR #119 extends the unsigned AAB gate with a stronger *binary* check.
CI retrieves Google's official bundletool-all-1.18.3.jar release asset and
MUST validate its published GitHub SHA-256 digest:
`a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29`.
A failed download/checksum aborts the gate before execution. The fixed
dependency is only used in CI; no Android API key, service-account token or
real Play upload certificate is needed.

The verified `bundletool dump manifest --module=base` output is parsed
and compared with five existing backend package identities and the Gradle
source. The decoded **release AAB** package, versionCode/versionName,
minSdk/targetSdk, INTERNET permission, and cleartext/backup/debug policy
must match; any disagreement fails CI. This closes the prior gap where a
valid ZIP bundle was accepted but its binary protobuf manifest was not
decoded. Synthetic XML and command contract tests cover negative cases.

This *does not* demonstrate Play Console ownership, Play App Signing
certificate, real user installation, live purchase, device-targeted
bundletool APK set or release eligibility. The bundle remains unsigned,
and the successful decoded report explicitly says `production=HOLD`.
The decoded manifest is transient CI evidence only, not a release artifact.

Official documentation:
https://developer.android.com/tools/bundletool
https://github.com/google/bundletool/releases/tag/1.18.3

## 14 November 2026 — PR #120: bundletool device-profile APK set simulations

The previous AAB manifest verification is preserved. GitHub CI now uses
the **same SHA-256 pinned official Google bundletool 1.18.3 jar** to run
`build-apks --mode=default` against the unsigned release-variant bundle.
A fresh, ephemeral **TEST-ONLY** RSA debug keystore is generated inside the
isolated CI runner. It is removed in the same shell step and NEVER uploaded.
Its local debug signature does NOT match or replace an authorized Google
Play Upload Certificate or Google Play App Signing key.

Four synthetic device specifications are kept under
`ci/orba_device_profiles`:
- API 26, arm64, Turkish/English locale, density 420;
- API 30, x86_64, Turkish/English, density 320;
- API 36, arm64, Turkish/English, density 480;
- API 36, x86_64, Turkish/English, density 320.

For each one `bundletool extract-apks` must create nonempty install
splits. CI verifies the set's `toc.pb`/ZIP integrity, validates profile
JSON, checks the compiled base package/version/SDK via real `aapt`,
verifies all extracted APK signatures with `apksigner`, and requires a
single consistent **ephemeral test signing certificate** across files.
It emits a separate GitHub artifact named
`orba-TEST-ONLY-device-apks-NOT-FOR-PLAY`, with SHA-256. It MUST NOT
be presented as the published APK or installed over an existing app with
a different signing key: doing so can fail or require uninstallation and
possible local data loss.

**This is device-profile extraction, NOT Android emulator execution,**
physical device compatibility certification, Play license testing, AAB
upload signing, store delivery, live subscription purchases or revenue.
CI ALWAYS returns `production=HOLD`,
`real_device_installation=NOT_TESTED`,
`android_emulator_execution=NOT_TESTED`, and
`real_google_play_distribution=NOT_TESTED`.
Before claiming practical device support, separate test-track installs
and API 26/30/36 emulator/device journeys are required.

Official: https://developer.android.com/tools/bundletool
