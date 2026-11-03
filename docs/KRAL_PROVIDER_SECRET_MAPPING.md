# KRAL: GitHub Actions provider configuration mapping

This document names configuration locations only. Do not put actual API keys,
tokens, signing materials, account passwords, or subscriptions in this file,
GitHub issues, pull requests, public logs, or chat messages.

## Target

Repository: `mehmetcerdik457-ctrl/Gpt-asistan`.

Configure credentials **only** through GitHub Settings > Secrets and variables >
Actions. Prefer an isolated environment with reviewer and branch restrictions.
Secret values must be provisioned by the authorized owner from an actual
provider or approved secret manager. A historical Drive inventory is not a
credential vault bridge and does not prove the key is current, owned, licensed,
or safe to reuse.

| Provider | Encrypted Actions secret (sensitive) | Actions variable (non-secret) |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `OPENAI_ALLOWED_MODELS` |
| Cloudflare Workers AI | `KRAL_CLOUDFLARE_API_TOKEN` | `KRAL_CLOUDFLARE_ACCOUNT_ID`, `KRAL_CLOUDFLARE_MODEL` |
| Owner Gateway | `KRAL_OWNER_GATEWAY_TOKEN` | `KRAL_OWNER_GATEWAY_URL`, `KRAL_OWNER_GATEWAY_HOST`, `KRAL_OWNER_GATEWAY_MODEL` |

Do not treat model names, IDs, URLs, or endpoint variables as authority to
read private conversations. Before moving any non-secret identifier into a
public repository variable, confirm that publishing it is appropriate.

## Proof sequence

1. Review and authorize each credential's source, scope, billing permissions,
   account ownership, and expiration. Rotate any value that was previously
   exposed in a document or Git history.
2. Add each permitted value to its designated encrypted GitHub Actions secret
   through the GitHub UI. Use scoped repository/environments.
3. Configure only non-sensitive model identifiers and routing data as GitHub
   Actions variables. If an identifier is confidential, store it as a secret
   and adjust the *boolean* gate accordingly instead of leaking it.
4. Rerun `kral-provider-presence.yml`. It checks **presence booleans only**,
   never values. A `CONFIGURED_NAME_FLAGS_ONLY` or
   `ALL_FLAGS_PRESENT_UNVERIFIED` outcome does not prove authentication,
   subscription, owner identity, billing approval, real inference, or
   Copilot credits.
5. Actual provider authentication, a bounded model response, Owner identity,
   cost acceptance, and PR review require **separate evidence and gates**.
   Never grant automatic broad GitHub writes or main-branch merge on the basis
   of these boolean checks alone.

## Current limitations

- Connected GitHub read/write functions in this ChatGPT session do not expose
  GitHub encrypted-secret updates. No credential transfer from Drive was made.
- Existing 50 GitHub-hosted jobs are bounded read-only processes, **not** 50
  Copilot model inference sessions.
- GitHub Actions `contents: read` and no persisted checkout credentials are
  intentional. Broadening these permissions requires task-specific review.
- The workflow fails closed when required configuration flags are absent.

Source branch: `integration/kral-secret-readiness-20261028`.
