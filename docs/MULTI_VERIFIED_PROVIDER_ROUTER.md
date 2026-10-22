# KRAL CORE — Existing providers in one opt-in verified router

This implementation reuses existing OpenAI, owner_gateway and Cloudflare
Workers AI Python adapters. It does not deploy a service, expose an endpoint,
recover a proprietary CİHAT API, or import any private model weights.

## Enable only after actual owner authorization

Default remains `KRAL_PROVIDER_MODE=openai`. The following opt-in setting
enables the *possibility* of probing up to 4 explicitly named models through
existing server adapters, which can incur inference charges:

```ini
KRAL_PROVIDER_MODE=multi_verified
KRAL_MULTI_ROUTER_APPROVED=YES
KRAL_MULTI_COST_APPROVED=YES
KRAL_MULTI_PROVIDERS=openai,cloudflare_workers_ai
```

Set these only when the owner separately approves incurred costs and the
server's enrolled Owner+Device P-256 authentication is operational.
Each underlying provider must also have correct vault-backed credentials
and its own allowlist and cost gate (Cloudflare additionally requires
`KRAL_CLOUDFLARE_COST_APPROVED=YES`). The two global flags default to NO.

## What changes in the existing gateway

- Model discovery probes only selected configured providers. Each verified
  model response preserves its own **real provider** label, not `verified_pool`.
- A failing provider probe does not remove another successful provider from
  the returned model choices; no unverified model is ever returned.
- If different providers return the *same bare model ID*, **both routes are
  blocked** because Android selects models using that ID alone.
- Revoking approval fails closed even for an earlier verified session.
- Model/chat requests use the owner-signed existing HTTPS API; conversation
  history/memory are opt-in, and replies remain bound to the selected provider.
- **No silent automatic fallback** to another commercial API exists. The owner
  must select the other model. This avoids sending private prompts to an
  unexpected party. Explicit owner-approved fallback is a later acceptance item.

## Evidence boundary

Synthetic test providers prove routing, deny conditions, history integrity,
collision rejection and one-provider-down isolation. They **do not prove**
actual Cloudflare/OpenAI credentials, independent live responses, a valid
owner-enrolled server, or physical Android acceptance.
