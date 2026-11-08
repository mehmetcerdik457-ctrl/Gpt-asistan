# KRAL Genesis 3.0 — UI onto 1.0.10 (no destructive replacement)

## Why this branch
This is a **new source-bound integration candidate** based on exact 1.0.10
`7c49114d8b8c4916a3bf59274863b537942a0c18`. The earlier
control-screen PR #95 was based on the **old 1.0.6 line** and diverged from
current PR #92. Replacing the modern `MainActivity.kt` with that older file
would lose OTP, backup, reminder and recent owner security logic.

Instead, three UI files were brought over as independent view-only components
from PR #95 source `b958c3d5dcfff5347919250363327a9e0d014118`,
and only the `buildContent` view assembly in the **modern** `MainActivity`
was adapted.

## Actual UI behavior
- **Sohbet**: conversation transcript, retained draft, send button and CİHAT/voice handoff.
- **Görevler**: the original `showMemoryMenu()`, `showLocalTaskMenu()`,
  and `showExpertMenu()` handlers. No automatic external actions.
- **Sistem**: the existing Model, server registration, Owner/Bridge
  status and TTS switch. Owner/Bridge status navigates back to the chat
  transcript before displaying a local read-only result.
- The model-connection state line stays visible across all tabs.
- Navigation only adjusts view visibility; it never invokes network/provider
  code or bypasses Android credentials.
- Strings `nav_chat`, `nav_tasks`, `nav_system` and warnings are Turkish.
  The Android app remains native Kotlin, with minSdk26/targetSdk36,
  not a web-only replacement.

## Source preservation constraints
The new branch deliberately leaves unchanged: `AndroidManifest.xml`,
`app/build.gradle.kts`, SQLCipher/key-management classes, all prior
database migrations, OTP code, `BackupUi` and restore pending state,
`LocalTaskReminders`, `OwnerGateway`, all model provider contracts,
activity lifecycle/notification-to-owner-lock behavior, permission handling
and `FLAG_SECURE`.

The only edits to original files are modern `MainActivity.kt` view assembly
and five additive `strings.xml` resources. Three UI files are additions.

## Acceptance gates
1. `./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
   :app:assembleDebugAndroidTest :app:bundleRelease --no-daemon`.
2. `python -m unittest discover -s server/tests -v` exact-head.
3. Android API30/36 emulator tests include
   `KralControlSectionsDeviceTest`: view switches, draft retention, 48dp
   targets and owner lock.
4. Owner email OTP, encrypted database persistence, source SHA, signing
   certificate, existing APK versionCode and installed-upgrade protection
   remain independent release gates.
5. Physical Galaxy S24/S26 and other Android device testing, voice service
   and actual owner-signed APK delivery are **NOT VERIFIED** in this branch.

**Do not merge this branch, deploy, install APKs, delete old builds or
publish to Google Play without independent CI + owner-approved release gates.**

Rollback: revert only this branch's additive UI commits. Never reset user data,
delete keystores or override the previous app's package-signing identity.
