# KRAL Genesis 3.0 — read-only installed APK identity gate

**Status:** Development-branch tool, not a device acceptance result. No actual
S24, S26 or other owner's handset was connected, queried or modified when this
file was authored.

## Why this exists

The existing scripts/check_android_upgrade.py compares two **local** APK files.
That does not prove the old APK file corresponds to the app actually installed
on the phone. scripts/inspect_installed_apk.py adds a strictly read-only device
inventory stage for that missing P0 fact.

The tool selects an **explicitly provided ADB serial** (no automatic device
selection), executes only adb shell pm path PACKAGE and adb pull for returned
installed APK paths, and checks every extracted base/split APK with local SDK
aapt and apksigner. Copies are deleted when inspection exits. It does not
read app-private databases, install/uninstall software, change device settings,
export keystores, rotate certificates, enroll accounts, or call external APIs.

The inspected device must be explicitly authorized for developer/ADB access.
Only a local trusted workstation with Android SDK/ADB should run it. **Never
paste a private device serial, token, database or keystore into a public issue,
CI log or support ticket.** The JSON result deliberately omits the serial and
temporary file paths.

## Inventory only — before a release candidate exists

Use the **actual authorized device serial** rather than the placeholder:

~~~bash
python3 scripts/inspect_installed_apk.py \
  --serial "YOUR_AUTHORIZED_ADB_SERIAL" \
  --package com.example.gptasistan.genesis \
  --adb adb \
  --aapt "$ANDROID_HOME/build-tools/36.0.0/aapt" \
  --apksigner "$ANDROID_HOME/build-tools/36.0.0/apksigner"
~~~

The only successful inventory status is
INSTALLED_APK_IDENTITY_OBSERVED_NOT_UPGRADE_APPROVAL. The result includes the
installed package ID, versionCode, SHA-256 of its pulled base APK, signing
certificate digest, whether the base APK is debuggable, and how many split APKs
were also inspected. All reported split APKs must match the base package, version
and signer. Any unreadable APK, missing base, mismatched split, invalid remote
path or missing SDK executable results in BLOCKED (exit code 2).

A supported Android OS version or an arm64-v8a build alone is **not** proof
that an existing owner installation can be safely updated.

## Optional release APK identity comparison

Only with a *real* owner-controlled, independently hashed, **non-debuggable**
candidate:

~~~bash
python3 scripts/inspect_installed_apk.py \
  --serial "YOUR_AUTHORIZED_ADB_SERIAL" \
  --package com.example.gptasistan.genesis \
  --candidate-apk /trusted/owner-release.apk \
  --expected-candidate-sha256 "64_HEX_CHARACTERS_FROM_TRUSTED_BUILD" \
  --expected-owner-cert-sha256 "64_HEX_CHARACTERS_FROM_OWNER_CERT_PIN"
~~~

Here the proposed APK must have the exact pinned file SHA-256, the same
verified signer and package ID, a higher versionCode, and debuggable=false.
When supplied, the public owner-certificate pin must also match. A success is
labeled APK_IDENTITIES_COMPATIBLE_NOT_INSTALLATION_PROOF and explicitly
reports upgrade_performed=false, upgrade_success_verified=false,
database_migration_verified=false, device_owner_verified=false and
play_accepted=false. Signing-key lineage / Play key rotation is not handled.

**The 6 November 2026 APK built at exact source
7c49114d8b8c4916a3bf59274863b537942a0c18 is a DEBUG candidate
(1.0.10 / versionCode 11). It is not a trusted owner release, and this tool's
optional release comparison must not be used to call it production ready.**
Its known SHA-256 is
f3341822e1e9b1ce252676df42086ee527ac9d3c2b6e93a78eaa338b2b054754.
Unsigned AAB is not a release.

## Testing and acceptance

- Pure fake-ADB tests: python -m unittest server.tests.test_installed_apk_probe -v.
- The CI Python test discovery includes these tests on a source-bound GitHub
  Actions run; a successful local mock does not mean the on-device command worked.
- Physical phone P0 acceptance additionally requires verifying the actual
  installed package, owner/credential gate, migration and encrypted data
  preservation, supported ABI/OS behavior, authorized signing and successful
  controlled upgrade. **This script never performs that upgrade.**
- No adb install, adb uninstall, wipe, restore, am start, root access or
  on-device write command exists in the implementation.

This effort must remain on a reviewed development branch. Do not merge main,
publish to Google Play, or instruct installation based solely on mock tests.
