# AI Platform Integration Matrix

This repository is the engineering control plane for the AI system. External services stay authoritative for their own credentials and data. GitHub orchestrates code, CI/CD, policy, evidence, and deployments.

## Connected control-plane services

| Capability | Preferred service | Repository use |
|---|---|---|
| Source / review / CI | GitHub | canonical code, PRs, Actions, security evidence |
| Primary model API | OpenAI Platform | runtime model and agent calls |
| Open model research | Hugging Face | models, datasets, Spaces |
| Primary Postgres runtime | Neon | persistent application state |
| Optional app backend | Supabase | auth, database, storage, edge functions when needed |
| Deploy | Railway / Vercel | backend and web/agent deployment |
| Rapid prototype | Replit | disposable prototypes and experiments |
| Observability | Datadog | logs, metrics, traces |
| Product / LLM analytics | PostHog | feature flags, product and LLM telemetry |
| Backup / documents | Google Drive / Dropbox | project evidence and off-repo backups |
| Knowledge | Notion | architecture and operating notes |
| Notifications | Slack | engineering alerts |
| Design | Figma / Canva | UI and product design |

## Rules

1. Never commit real credentials, tokens, keystores, recovery codes, or private keys.
2. Prefer provider-native secret stores, GitHub Environments/Actions secrets, and short-lived OIDC credentials.
3. Keep production and test credentials separate.
4. Use least privilege. Read-only connectors stay read-only unless a write capability is actually needed.
5. Every production integration must have an owner, rotation path, revocation path, and test that proves wiring without printing the secret.
6. A connector being installed does not prove that the external account is authenticated. Authentication must be verified by a harmless live read.
7. A successful PR check proves only the tested commit/event. Do not reuse historical PASS claims for a newer HEAD.
