# KRAL — Existing owner signer and explicit readiness evidence

## 1.0.7 continuation — 2026-11-04

The current owner instruction authorizes main integration and APK delivery.
`config/android-owner-signing.json` now additionally permits the same owner
actor's push to `main` for release APK/AAB signing. The existing historical
branch remains the only context for candidate/instrumentation re-signing.
The public certificate pin and four existing secret names below are unchanged.

The release and debug variants both keep `com.example.gptasistan.genesis`;
versionCode is 8. APK ABI splits are disabled and the four existing native ABIs
are explicit. Release is non-debuggable. Release outputs are post-signed with
the existing key, then checked for matching APK/AAB identity, content and pin.

The trusted main workflow checks secret availability before attempting release
signing. Missing keys produce `BLOCKED_OWNER_SECRETS_MISSING` evidence; the
signed-release jobs are skipped. A separate, clearly labelled debug prerelease
may publish only after Python/JVM/Lint and API 30/36 candidate checks pass.
It does not satisfy owner release signing or phone upgrade compatibility.
Configured secrets with an invalid keystore or mismatched certificate cause
the signing path to fail. No replacement key is generated.

The following sections preserve the original 1.0.6 design and its provenance.

## What changes

The source and functional APK delivery from PR #86 are preserved. This continuation
adds a path for the **existing** owner signing identity, using the four names
already referenced by the repository's 2026-09-29 owner build:

| Existing GitHub Secret | Purpose |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Existing keystore bytes, base64 encoded |
| `ANDROID_KEY_ALIAS` | Existing signing alias |
| `ANDROID_KEY_PASSWORD` | Existing private-key password |
| `ANDROID_STORE_PASSWORD` | Existing keystore password |

No new signing key, credential, OAuth grant, repository permission or production
deployment is created. Never put these values in chat, source, PR text, logs or
artifacts. Existing repository secrets can be configured by their owner at:
https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/settings/secrets/actions

## Pinned identity and execution boundary

The public certificate SHA-256 pin is preserved from commit
`7228a9ecd9f2a3d1ed5402b39d72f2e31994952e`, file
`.github/workflows/owner-feature-parity-build.yml`:

`279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448`

This historical pin is a verification constraint, not a claim that credentials
are present today or that the phone's installed KRAL APK uses this certificate.
Only the repository owner actor's push to `fix/kral-owner-signing-20261103` may
use these secrets. PR builds and other refs/actors never read them. The workflow
keeps `contents: read`; it does not use `pull_request_target`.

The keystore is decoded only inside a private temporary directory outside the
uploaded workspace. Its public certificate must match the pin before signing.
Both the application and instrumentation APK must verify with that certificate
before either build output is replaced. Temporary signing files are cleaned by
the helper. Tool stderr, aliases, passwords and keystore contents are not logged.

## Published evidence, including a real BLOCKED outcome

`signing-status.json` is included beside the APK and test summary. It is bound to
the source commit and run. Metadata does not call the APK owner-signed unless the
actual `apksigner` certificate matches the verified public pin.

- `OWNER_SIGNER_PIN_VERIFIED`: the existing credential was used and both APK
  signatures matched the pin. This still does not prove a phone upgrade.
- `BLOCKED_OWNER_SECRETS_MISSING`: names missing from the trusted job are listed,
  never their values. A functional debug APK can still be built and tested; it
  remains explicitly marked as not owner-signed.
- `DEBUG_ONLY_UNTRUSTED_EVENT`: a PR or other untrusted event uses no signing
  secret. Its debug APK must not be confused with a trusted-push signing result.
- Invalid encoding, certificate mismatch or tool failure stops the signing/build
  path; it cannot silently publish an owner-signed success.

## Previous installations remain protected

The 1.0.4 and 1.0.5 debug APKs used different ephemeral CI certificates. Existing
`check_android_upgrade.py` continues to reject their certificate mismatch. A
private key cannot be reconstructed from an APK's public certificate. This change
does not recover the old ephemeral key, rotate an installed app's identity,
uninstall the app, reset data, import a database, or claim data migration.

Even when the historical owner key is available, compatibility with a currently
installed APK must be checked against that APK's actual package/certificate and
version. `previous_install_upgrade_verified` therefore stays false in every
signing report until there is separate device/upgrade evidence.

The candidate is version `1.0.6-genesis-candidate`, versionCode `7`, same package
`com.example.gptasistan.genesis`. main and prior APK/evidence files stay intact.
