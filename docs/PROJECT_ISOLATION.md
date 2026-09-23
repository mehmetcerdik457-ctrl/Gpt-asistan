# Project Isolation Policy

The shared GitHub platform may provide reusable security and CI building blocks, but project evidence and authority must remain isolated.

## Isolated domains
- GitHub Master Platform
- MEHMET APK — OWNER EDITION
- Public APK Forensic
- Hatice/Zelal
- Emrullah
- other independent workspaces

## Mandatory boundaries
- Do not reuse production credentials, signing keys, datasets, release artifacts, forensic evidence, caches, or environment secrets across isolated domains.
- Do not treat a test, hash, approval, attestation, or release from one project as evidence for another.
- Use project-specific branches/repositories, environments, artifact names, release channels, and secret scopes where available.
- Public APK forensic inputs are immutable evidence and must never be mixed with Owner Edition signing/build material.
- Shared workflows must fail closed when project identity is ambiguous.

## Cross-project reuse
Only non-secret, versioned infrastructure such as reusable workflows, policy validators, devcontainer definitions, and documentation templates may be shared. Shared infrastructure does not share authorization.
