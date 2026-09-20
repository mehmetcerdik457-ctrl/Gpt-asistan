# Security Policy

## Reporting

Do not post credentials, private keys, tokens, keystores, personal data, or exploit details in public issues.

Use GitHub's private vulnerability reporting feature when it is enabled for this repository. Otherwise contact the repository owner privately through a trusted channel.

## Security baseline

- Secrets belong in approved secret stores, never in the repository.
- CI permissions must be least privilege.
- Third-party GitHub Actions must be pinned to immutable commit SHAs.
- High-impact external actions require explicit owner authorization and verification.
- Do not weaken authentication, signing, authorization, or audit controls to make a test pass.
