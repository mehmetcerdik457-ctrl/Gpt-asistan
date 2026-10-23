# KRAL Android to OMEGA real TLS in CI emulator
Pinned source: OMEGA PR #96 fd34e1a6b57b13644c6f2053fe97e86b485de10b; existing KRAL PR #46.

This adds a **test-only** Android TLS connection test to the existing application.
OMEGA backend's actual handler runs on CI host **127.0.0.1:18443** with
an ephemeral one-day self-signed certificate. The Android 11 emulator uses
`adb reverse` to connect over HTTPS. The androidTest-only connection trusts
that generated certificate with a test-scoped SSLContext and preserves default
hostname verification (IP SAN 127.0.0.1). A second test checks that the
**unchanged production fetch path rejects** the self-signed certificate.

The ephemeral DER trust anchor is generated at CI runtime under androidTest
assets, not packaged in the production app APK. No user data, Owner keys,
or real provider credentials, and no public host port. The test insists
the OMEGA health response reports Owner not enrolled and execution disabled;
models and chat are also verified 403 before Android tests.

This is **not** a physical device, real public server, trusted production TLS
certificate or Owner enrollment test, and does not make OMEGA production-ready.
The source repositories and signed historical apps are preserved; main untouched.
