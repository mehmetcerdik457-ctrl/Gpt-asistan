# Security Policy

## Supported Branch
Security fixes are maintained on `main` and validated through pull requests and CI.

## Reporting a Vulnerability
Please do not publish exploitable details in a public issue. Use GitHub's private vulnerability reporting / Security Advisories interface when available for this repository. If that interface is unavailable for your account or plan, contact the repository owner privately through the account contact method.

## Handling Rules
- Do not commit secrets, signing keys, keystores, tokens, or private credentials.
- Do not weaken Android signing, TLS validation, authentication, or permission checks merely to make tests pass.
- Security-relevant changes should include reproducible verification evidence.
