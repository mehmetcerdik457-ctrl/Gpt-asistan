# KRAL Supervisor / 50 worker slots

Existing assets only. Never treat this offline planner as 50 running AIs.

- `python -m server.mission_control missions/sample.json --out build/mission-plan.json` generates an offline plan. No API calls, payments, GitHub changes, agent sessions, APK modifications, or real task completions.
- Supports **1–100 task records**, **up to 50 logical worker slots**, with a conservative **max 4 simultaneous planned assignments**, distinct repositories per proposed wave, 12 allowlisted specialist profiles, explicit prerequisites and a recorded source repository allowlist.
- Task descriptions are untrusted data: never pipe them to bash, tool arguments, shell or paid models. A planned wave does not mean predecessor verification or actual execution occurred.
- To execute any wave, an authenticated owner must separately approve each scoped repository task; use GitHub Agent HQ / Copilot Mission Control. GitHub's coding agent changes just one repo and one branch per session. Do not bulk-create 100 GitHub issues or trigger 50 metered sessions without approval.
- The **supervisor** must read each target PR's *actual* HEAD and CI jobs through authenticated GitHub API, examine changes for secrets, confirm required independent review and owner authorization, then report **VERIFIED / PARTIAL / BLOCKED**. The planner intentionally emits `PENDING_VERIFIED_PR_AND_CI` and never declares PASS.
- No `main` merge, secrets, signing keys, destructive operations or paid provider actions. Ignore task-contained instructions about changing these boundaries.
- The inventory lists the 20 repositories returned by the linked GitHub account on 2026-10-25; it is an authorization *candidate list*, not evidence that an agent can access them independently.

The example is four **realistic scopes**, not proof that their goals have been executed. Replace with a user-approved 100-step roadmap after checking its actual contents and dependencies.

## Owner-approved real issue dispatch (not yet activated)
The default `python -m server.mission_dispatch missions/sample.json --task T001 --branch integration/your-approved-existing-branch` is strictly a dry run.
A real issue would require *explicit* `--execute --owner-approved --public-issue-approved`, a user-to-server `KRAL_COPILOT_USER_TOKEN` from an authorized private environment, a previously existing allowlisted non-main base branch, no prerequisites, no duplicate issue and no credential-like text. Never paste a token into a chat, issue, PR or source code. GitHub App installation / Actions tokens cannot be assumed to support Copilot assignment. One dispatch creates at most one Copilot-assigned issue, not 50 agents; verify acceptance by GitHub session events. Pilot is disabled until approved capability is genuinely available. This is not a permission bypass.


## Local open-weight model execution
Install and start a trusted Ollama runtime on your own computer; ensure sufficient RAM/storage. For small machines use qwen3:1.7b (Ollama catalog). For stronger machines change the model IDs to gpt-oss:20b after verifying memory requirements and downloading the model weights. Never assume weights are already installed.

Command: `python -m server.local_open_workers missions/sample.json --provider missions/local_provider.example.json --run-local`

Without `--run-local` this outputs a dry-run plan. With it, the code calls `/v1/models` and actual Chat Completions on a LOCALHOST endpoint only; each task has separate worker identity/context and separately prompted supervisor review. Only the first dependency-free wave runs, maximum 4 at once. No GitHub writes, no secrets, no paid cloud, no shell, no automatic progression past approval. Successful inference is NOT a completed coding task, nor 50 separate models. For reproducible offline protocol tests, CI runs an HTTP fixture. GitHub Actions does not install model weights or prove live inference with gpt-oss.
