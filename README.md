# Gpt-asistan

Security-focused AI engineering control plane for building, testing, deploying, and auditing the Mehmet AI system.

## Core architecture

- **GitHub**: canonical source, pull requests, CI/CD, supply-chain evidence, security policy.
- **OpenAI Platform**: primary model/agent API.
- **Hugging Face**: open-model research and evaluation.
- **Neon / Supabase**: persistent state and backend services.
- **Railway / Vercel**: deployment.
- **Datadog / PostHog**: observability and product/LLM telemetry.
- **Google Drive / Dropbox**: off-repository backup and evidence.
- **Slack / Notion**: notifications and knowledge.

## Security posture

- third-party Actions are pinned to immutable SHAs;
- checkout credentials are not persisted;
- workflows use explicit least-privilege permissions;
- CodeQL covers Android/Java-Kotlin plus Python and GitHub Actions;
- release evidence includes hashes, SBOM and provenance paths;
- secrets, keystores and private credentials are forbidden in source control;
- OpenAI paid acceptance calls are explicit opt-in.

## Evidence rule

A build, scan, deployment, artifact, signing state, API integration, or device state is PASS only when evidence from the exact tested commit/runtime proves it.
