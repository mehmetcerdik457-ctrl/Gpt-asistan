# KRAL 12-agent source recovery — 2026-11-03

Twelve existing Copilot role profiles were copied from the preserved
`integration/kral-50-worker-supervisor-20261025` GitHub branch into this
draft integration line. They were NOT generated from scratch or counted as
twelve live paid model sessions. Original role definitions remain on the source
branch, unchanged.

The master profile's historical YouTube MCP declaration was intentionally
**not** activated: its `kral/mcp/youtube_server.py` executable and
OAuth environment are not integrated or verified on this target branch.
Historical profile is preserved upstream for a future separate read-only review.
No OAuth, billing, GitHub secret or third-party connection is created.

Evidence:
- 12 .agent.md files recovered and validated by tests.
- 50 independent read-only GitHub Actions worker jobs + one final verifier
  SUCCESS: https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/40679674812
- 50 logical slots and at most four local read-only workers are separately
  implemented in `server/owner_workers.py`.
- OpenAI Responses Multi-agent beta is a *third*, separate provider feature;
  no hosted subagents or billable calls are enabled by these files.

Passing Python static tests proves role definitions are present and the
read-only metadata safeguards hold; it does not prove GitHub Copilot or its
custom agent scheduler is connected/active at runtime.

No merge into `main`, no Play release, no device installation.
