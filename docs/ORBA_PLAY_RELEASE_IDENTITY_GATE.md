# ORBA Google Play release identity gate — draft PR #117

This file is a **release safety checklist**, not evidence that ORBA Studios
owns or has published a Google Play app with the current application ID.

## Checks performed automatically
- `server/play_distribution_preflight.py` compares Android Gradle
  `applicationId` to five independent Python Play back-end modules:
  entitlement, subscriptions v2 API, acknowledgement, RTDN and voided orders.
- Checks `versionCode`, SDK bounds, pinned Billing library dependency,
  manifest INTERNET permission, `allowBackup=false` and cleartext denial.
- Once the *debug* APK is built, CI calls installed Android SDK
  `aapt dump badging` to compare actual compiled package name, version,
  minimum/target SDK and debuggability to the Gradle sources.
- `apksigner verify --print-certs` proves that the tested debug APK
  has a verifiable signing certificate. A debug certificate is **not**
  a Google Play App Signing/upload certificate.
- Product ID input validation in Android now matches the backend limit:
  ASCII letters/digits, underscore/dot, length 1–100.

All successful offline runs report `production=HOLD`; consistency
**does not imply Google Play Console ownership or valid store products**.

## Mandatory external acceptance evidence (NOT provided by CI)
1. Confirm that ORBA Play Console contains a verified application with
   **exact** package `com.example.gptasistan.genesis`. If not, do not
   rewrite `main` or migrate existing installed user data; decide a
   signed, reviewed package strategy first.
2. Independently verify subscription product IDs, base plans and offers
   under that same Play Console app. Existing synthetic
   `orba_pro_monthly` examples **are not proof of products**.
3. Verify Play App Signing and upload key certificates, monotonically
   increasing Play `versionCode`, release AAB provenance, device catalog,
   Android minimum/target SDK compatibility and test-track access.
4. Register license testers; test a Play-distributed installation and
   test payment method, including renewals, cancellations, grace, hold,
   expiry and voided purchases. Debug APK CI alone is insufficient.
5. Approve scoped Google service account, app-specific Play Console API
   permissions, Pub/Sub OIDC, server secrets and RTDN deployment without
   exposing credentials in GitHub issues or Android APK.
6. Obtain explicit owner review before enabling production billing or
   merging to `main`; preserve rollback and historic artifacts.

### Official Google guidance

- https://developer.android.com/google/play/billing/test
- https://developer.android.com/studio/publish/upload-bundle
- https://developers.google.com/android-publisher/getting_started

**Current conclusion: PRODUCTION HOLD.** The source package is known, but
its exact match to ORBA Play Console is NOT independently verified.
