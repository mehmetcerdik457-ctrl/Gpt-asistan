# Disaster Recovery Runbook

Recovery evidence must be tied to an exact repository state and must not expose secrets.

## Repository loss or corruption
1. Freeze writes and record the last trusted commit, tag, release, workflow run, and artifact hashes.
2. Restore from a separately held repository/configuration backup.
3. Compare restored refs and critical files against trusted hashes.
4. Re-run CI, CodeQL, dependency review, build, SBOM, reproducibility, and backup checks before reopening releases.

## Compromised GitHub account
1. Revoke suspicious sessions and credentials using GitHub account security controls.
2. Rotate affected repository, cloud, signing, and integration credentials according to exposure.
3. Audit repository, Actions, release, collaborator, application, and authorization history.
4. Treat commits/releases created during the suspected window as untrusted until independently verified.

## Compromised token or secret
1. Revoke first.
2. Rotate dependent credentials and invalidate sessions where applicable.
3. Search repository history, workflow logs, caches, artifacts, releases, packages, and external logs without republishing the value.
4. Verify replacement credentials through least-privilege runtime tests.

## Malicious commit, dependency, Action, or PR
1. Block merge/release and identify the first affected SHA.
2. Preserve evidence.
3. Revert or replace the malicious change without weakening review gates.
4. Rotate credentials if exfiltration was possible.
5. Rebuild from a trusted SHA and compare SBOM, provenance, and artifact hashes.

## Recovery gate
Recovery is VERIFIED only after the restored current state passes the required checks and restored artifacts are bound to their source SHA and hashes. A backup file alone is PARTIAL.
