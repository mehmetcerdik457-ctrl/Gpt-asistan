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
