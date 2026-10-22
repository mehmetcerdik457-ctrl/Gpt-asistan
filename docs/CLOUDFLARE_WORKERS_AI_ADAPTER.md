# Opt-in KRAL Cloudflare Workers AI Adapter

This adds a provider to the EXISTING KRAL server; it does not create Workers, an AI Gateway, tokens, billing, or a new project. Account-level catalog access is not a live model connection.

Enable only with owner-approved, scoped server-side secret storage and accepted inference costs: KRAL_PROVIDER_MODE=cloudflare_workers_ai, KRAL_CLOUDFLARE_ACCOUNT_ID (32 lowercase hex), KRAL_CLOUDFLARE_MODEL (@cf/vendor/model) and KRAL_CLOUDFLARE_API_TOKEN. Cost guard: configure KRAL_CLOUDFLARE_COST_APPROVED=YES only after separate owner approval of possible inference charges. Its safe default is NO; an API token alone cannot authorize model requests. Default provider stays openai.

Endpoint: POST https://api.cloudflare.com/client/v4/accounts/ACCOUNT_ID/ai/run/MODEL. Provider route, account, HTTPS hostname and content type are fixed. Unknown model, malformed response, redirects, auth errors and missing token fail closed. No implicit fallback.

The pinned model route is not an upstream-echoed identity. The adapter accepts REST result.response string only; models with incompatible schemas require separate review. Synthetic tests do not mean LIVE_TESTED. Signed Owner+Device request and actual model response are required for acceptance; Android hardware acceptance is separate. No key belongs in GitHub, Drive, APK or log.
