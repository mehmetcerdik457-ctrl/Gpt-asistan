# Control Plane Baseline

Purpose: platform hardening only.

Rules:

- Gpt-asistan is not production Cihat AI source.
- Production credentials are forbidden.
- Production deployment changes are forbidden.
- Security-relevant changes require evidence.
- Connector permissions must be explicit.

Verification:

- File existence check.
- Pull request review.
- CI validation before merge.
