# Android Owner → OMEGA v1 signing candidate (NOT DEPLOYED)

Source: Gpt-asistan PR #36; follows public backend PR #94.

- OmegaV1Envelope.canonical() makes exactly the body/path/identity/timestamp/nonce UTF-8 message required by Python owner_auth_v1.canonical.
- OwnerOmegaV1Signer.signedHeaders() uses a separate Owner AndroidKeyStore P-256 key plus the existing registered TrustedDeviceManager Keystore private key. Both require a fresh Owner session (<=30s); revoked device rejected. No private key is exported and no OpenAI key is copied.
- devicePublicDerBase64 and ownerPublicDerBase64 only export public DER. This is NOT trusted enrollment: administrator must verify human/device identity and provision pinned public keys on backend. Never auto-enroll from network input.
- The Android signer does NOT send HTTP calls until an authenticated enrollment channel and approved TLS trust config are available. Fail-closed; never route to arbitrary hosts or send the existing client OpenAI provider secret to backend.
- Release signer/physical phone validation pending. Unit tests check canonical bytes and input refusal; no APK was modified or installed.