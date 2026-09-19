# Secret Handling Contract

## Storage hierarchy

Use the narrowest provider-native store available:

1. Cloud/provider deployment secret store for runtime-only credentials.
2. GitHub Environment secrets for environment-scoped CI credentials.
3. GitHub Actions repository secrets only when an environment-specific secret is not appropriate.
4. Local encrypted credential storage for developer-only credentials.

Do not place secret values in source files, issues, PR bodies, workflow logs, artifacts, documentation, screenshots, or chat transcripts.

## Core secret map

| Variable | Purpose | Preferred location |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI runtime / acceptance test | GitHub Environment `openai-ci` and deployment provider secret store |
| `HUGGINGFACE_TOKEN` | private HF resources, if needed | deployment/provider secret store |
| `DATABASE_URL` / `NEON_DATABASE_URL` | Postgres connection | deployment provider secret store |
| `SUPABASE_SERVICE_ROLE_KEY` | privileged Supabase backend access | server-only secret store |
| `VERCEL_TOKEN` / `RAILWAY_TOKEN` | deployment automation, only if OIDC/provider integration is unavailable | GitHub Environment secret |
| `DATADOG_API_KEY` / `DATADOG_APP_KEY` | observability | deployment/provider secret store |
| `POSTHOG_API_KEY` | product/LLM telemetry | deployment provider secret store |
| `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` | notifications/bot | deployment provider secret store |
| Android signing variables | release signing | protected release environment only |

## Rotation

If a secret may have leaked:
1. revoke/rotate it at the provider first;
2. replace it in the secret store;
3. invalidate dependent sessions when applicable;
4. inspect git history, Actions logs, artifacts, and deployments without republishing the value;
5. rerun the smallest safe acceptance test.

## CI acceptance rule

Secret-wiring checks must prove presence or functionality without echoing the credential. Paid external API probes must be opt-in unless a release gate explicitly requires them.
