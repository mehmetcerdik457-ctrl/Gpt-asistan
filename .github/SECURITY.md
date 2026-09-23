# Security Policy

## Supported Branch

Security fixes are maintained on `main` and validated through pull requests and CI evidence.

## Reporting a Vulnerability

Do not publish exploit details, credentials, private architecture, private datasets, or other sensitive material in a public issue.

Use GitHub private vulnerability reporting / Security Advisories when available. If private reporting is unavailable for the account or plan, contact the repository owner through a private authenticated channel and include the affected commit or release, impact, prerequisites, minimal reproduction steps, and suggested remediation when known.

## Secret Handling

Secrets, API keys, access tokens, signing material, keystores, recovery codes, private datasets, and production configuration must never be committed.

If exposure is suspected:

1. Revoke or rotate the credential immediately.
2. Invalidate dependent sessions or credentials where appropriate.
3. Remove the secret from active configuration.
4. Investigate repository history, workflow artifacts, and logs without republishing the secret.
5. Record the incident and remediation evidence.

## Supply-Chain Policy

- Pin third-party GitHub Actions to immutable commit SHAs.
- Review dependency updates before merge.
- Produce SBOM, hashes, and provenance evidence for release artifacts.
- Prefer short-lived OIDC/federated credentials over long-lived cloud secrets where supported.
- Do not weaken signing, TLS validation, authentication, permission checks, or review gates merely to make tests pass.

## Android and Release Handling

Production signing keys, keystores, device-owner credentials, and release secrets must remain outside source control. Security-sensitive changes should include reproducible verification evidence before release.
