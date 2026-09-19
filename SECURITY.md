# Security Policy

## Supported branch

Security fixes are maintained on the default branch and current release line.

## Reporting a vulnerability

Do not open a public issue containing secrets, credentials, exploit details, private architecture, private datasets, or other sensitive material.

For now, use GitHub's private vulnerability reporting interface when available. If private reporting is not enabled for the repository, contact the repository owner through a private authenticated channel and include:

- affected commit or release;
- impact and prerequisites;
- minimal reproduction steps;
- suggested remediation, if known.

## Secret handling

Secrets, API keys, access tokens, signing material, recovery codes, private datasets, and production configuration must never be committed to this repository.

If a secret is exposed:

1. revoke or rotate it immediately;
2. invalidate dependent sessions or credentials where appropriate;
3. remove it from active configuration;
4. investigate repository history and workflow logs;
5. document the incident without republishing the secret.

## Supply-chain policy

GitHub Actions should be pinned to immutable commit SHAs. Dependency updates should be reviewed before merge. Production secrets should use short-lived federation/OIDC where supported rather than long-lived static credentials.
