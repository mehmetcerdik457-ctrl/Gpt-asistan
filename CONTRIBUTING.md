# Contributing

This repository is operated as an evidence-driven engineering control plane. Changes must be reviewable, reproducible, and tied to an exact Git commit.

## Workflow

1. Work on a branch and open a pull request. Do not bypass protected-branch controls.
2. Keep changes scoped. Separate unrelated refactors from security or release changes.
3. Record the exact head SHA used for verification.
4. Allow CI, dependency review, CodeQL, build, reproducibility, forensic, and backup checks to reach terminal state before claiming success.
5. If the head SHA changes, treat previous check results as historical evidence, not proof for the new head.
6. Do not merge without explicit repository-owner approval.

## Security

Never commit passwords, API keys, access tokens, signing keys, keystores, recovery codes, private certificates, or other secrets. Follow `.github/SECURITY.md` for vulnerability reporting.

Do not disable authentication, TLS verification, signing checks, dependency gates, or other security controls merely to obtain a green build.

## Evidence expected in pull requests

Include the relevant workflow run IDs, test results, device/build information when applicable, and artifact hashes for release-sensitive work. Claims such as "verified", "secure", or "production ready" require corresponding evidence.
