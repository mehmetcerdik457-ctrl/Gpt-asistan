# AGENTS.md

## Repository identity

This repository is `Gpt-asistan`. Work only from artifacts and evidence belonging to this repository unless the owner explicitly supplies another source.

## Engineering rules

- Reuse working code before redesigning.
- Prefer the smallest real working vertical slice.
- Never claim PASS without traceable evidence.
- Use VERIFIED, PARTIAL, NOT_CONFIGURED, NOT_TESTED, FAILED, BLOCKED, USER_ACTION_REQUIRED, or NOT_APPLICABLE.
- Keep credentials and secret values out of source, logs, prompts, artifacts, and reports.
- Treat external model/API providers as replaceable workers, not the identity or authority core.
- High-impact actions require explicit owner authorization and verification.
- Do not silently weaken security gates.
- Do not import code, credentials, artifacts, or conclusions from unrelated projects.
- GitHub Actions must use least-privilege permissions and immutable action SHAs.

## Pull requests

Prefer branch + PR. Record the exact HEAD SHA used for verification. If HEAD changes, rerun the affected checks.
