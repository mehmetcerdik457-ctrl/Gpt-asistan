# KRAL GENESIS — Owner-signed source inspection (draft)

POST /api/v1/owner/sources accepts JSON with exactly two fields:
{"action":"inspect","source_id":"source.apk"}

Authorization: the gateway's unchanged dual P-256 Owner/device signatures, nonce
and timestamp. Unauthenticated requests fail before scanning. The owner chooses
the dedicated read-only directory on the server through KRAL_SOURCE_ROOT.
The API body cannot supply or override that root. Default empty = disabled.

Responses contain a bounded SHA-256 evidence record and, for APK files, central
directory structure hints: AndroidManifest presence, DEX count, native ABI
and .so count. ZIPs are never unpacked and files are never executed.
SHA and ZIP evidence do not prove signing, installation, package identity,
model access, permissions, capability acquisition, or a phone test.

Before enabling, independently verify the real Owner/device enrollment, HTTPS,
dedicated read-only mount, and private storage. Never mount /, credential vaults,
cloud token stores, or uncontrolled writable directories as KRAL_SOURCE_ROOT.

Source paths with traversal, hidden or secret-like names, symlinks, unsupported
extensions or oversized files fail closed. Unknown API fields are refused.

CI can verify static route behavior and unsigned HTTP denial only. Actual
Owner phone -> signed HTTP -> source file -> response acceptance is still blocked
until the genuine device and server infrastructure can be tested.

No main merge, release, provider activation or deployment in this PR.
