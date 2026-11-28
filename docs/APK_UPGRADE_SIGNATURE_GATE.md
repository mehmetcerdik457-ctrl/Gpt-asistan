# KRAL APK Upgrade Gate — No data loss by accidental uninstall

## Purpose
The KRAL candidate APK produced by GitHub Actions is currently DEBUG-signed
and uses the application ID `com.example.gptasistan.genesis`.
Its signing certificate has varied across CI runs. A different signing
certificate cannot normally update an installed Android package in place.
Uninstalling the existing app can destroy local chat, memory, tasks and SQLCipher
key material. **Never uninstall, reset app data, bypass signature checks or
replace keys simply to install a new candidate.**

This project intentionally does NOT create, export, upload or rotate signing keys.

## Offline APK-to-APK check

On a trusted computer with Android SDK build-tools installed, obtain:
1. A verified copy of the **currently installed** APK (source provenance and owner
   approval required; obtaining it is outside this script).
2. The exact proposed candidate APK and its published SHA-256 metadata.
3. Local Android SDK `aapt` and `apksigner` binaries.

Example:

```bash
python3 scripts/check_android_upgrade.py \
  --previous-apk /trusted/previous.apk \
  --candidate-apk /trusted/candidate.apk \
  --expected-candidate-sha256 "<expected-64-hex-build-evidence>" \
  --aapt "$ANDROID_HOME/build-tools/<installed-version>/aapt" \
  --apksigner "$ANDROID_HOME/build-tools/<installed-version>/apksigner" \
  --require-release
```

The `--expected-candidate-sha256` value is **mandatory**. Copy it from trusted,
independently verified APK build evidence. The optional
`--expected-previous-sha256` checks a previously trusted local APK copy.
The tool re-hashes both files after SDK inspection to reject local file changes
during the check.

The gate fails (exit code 2) when the package ID differs, the verified signing
certificate SHA-256 differs, the proposed `versionCode` is not strictly
greater, SDK metadata/signing verification is missing, or a requested release
candidate is debuggable. It **does not** install an APK or access an Android phone.

## Important acceptance boundaries

- A PASS only means **the two supplied APK files have compatible checked
  identities**. It does NOT prove the "previous" file represents the exact
  installed application, the phone accepts the upgrade, or data survived.
- Signing key lineage / official Play App Signing key rotation is NOT evaluated;
  such cases need a separate documented Android/Play verification path.
- CI debug signing identity is not a release signing identity.
- The current candidate `versionCode=4` is unchanged: this check will
  correctly BLOCK using it as a version-increasing upgrade from another
  `versionCode=4` APK.
- The debug candidate uses package `com.example.gptasistan.genesis`;
  a Play release with package `com.example.gptasistan` is **a different app**.
  Do not mistake installing both for in-place upgrade or data migration.
- Never send signing keys, keystore passwords, app databases or device backups
  to a CI log, issue, PR, or external service.
- Release readiness also requires encrypted data migration, key retention and
  backup/restore procedures, physical-device testing, owner approval, signing
  strategy, and Play Console acceptance.

**Current status:** gate written and regression tested; no actual owner-device
installed APK was provided, and no live in-place upgrade has been verified.
