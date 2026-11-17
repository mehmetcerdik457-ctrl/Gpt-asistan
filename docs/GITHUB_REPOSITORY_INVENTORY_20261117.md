# GitHub repository inventory for KRAL — 2026-11-17

## Scope and method

Read-only inventory through the currently connected GitHub account. The repository listing returned 20 accessible repositories; each repository's default-branch tree and repository metadata were inspected. Selected README, project-scope, and implementation files were opened where relevant. This is not a full source-code audit of every repository.

No repository settings, secrets, branch protections, visibility, releases, or default branches were changed. No other repository was modified.

## Inventory

| Repository | Visibility / type | Finding | KRAL action |
| --- | --- | --- | --- |
| `Gpt-asistan` | Public, owned, default `main` | Active KRAL Android/backend repository; Gemini/OpenAI provider and owner-gateway code is being changed only on the feature branch documented in PR #125. | Primary integration target |
| `.github` | Public, owned | Shared community-health files; README says global templates. | No runtime connector |
| `mehmetcerdik457-ctrl` | Public, owned | Profile repository. | No runtime connector |
| `repo-template` | Public, owned | Starter template. | No runtime connector |
| `studio` | Public, owned | Description: repository generation and automation scripts. | Candidate for later automation review; not yet inspected file-by-file |
| `doktor` | Public, owned | Description: error analysis and diagnosis; README identifies it as a project template. | No proven KRAL integration |
| `hata-ayiklayici` | Public, owned | Description: debugger/log helpers; README identifies it as a project template. | No proven KRAL integration |
| `termux-mods` | Public, owned | Termux configuration and script collection. | No proven KRAL integration |
| `apk-starter` | Public, owned | Android APK build starter template. | No proven KRAL integration |
| `bot-starter` | Public, owned | Bot application starter template. | No proven KRAL integration |
| `serverless-starter` | Public, owned | Serverless service starter template. | No proven KRAL integration |
| `benim-uygulamam` | Public, owned | Separate PROJECT OMEGA repository. Its `scope.yaml` says the OMEGA project is limited to its own checkout and marks GitHub APIs, Google Cloud, Drive, and external integrations as unverified/not authorized or provisioned. | Read-only reference only; no changes and no credentials assumed |
| `Magisk` | Public fork | Upstream Android root-management project; 891 tree entries inspected. | Not a KRAL connector |
| `telefon-yedek` | Public, owned | Contains `GPTMobile-v0.6.3.apk`; binary not inspected in this inventory. | Preserve as a separate artifact; provenance/security audit remains outstanding |
| `Shizuku` | Public fork | Upstream Android privileged API bridge. | Not wired to KRAL |
| `codespaces-react` | Public fork | React/Codespaces project. | No proven KRAL integration |
| `openai-agents-python` | Public fork | OpenAI Agents SDK source tree. | Candidate reference for later agent orchestration; no dependency added |
| `docs` | Public fork | Railway documentation. | No KRAL runtime connector |
| `rish-mcp` | Public fork | Android shell MCP relay/agent. README says preview, outbound WebSocket relay, bearer-token MCP access, and that real-device release gates remain in progress. | High-privilege device bridge candidate; not integrated or authorized for KRAL actions |
| `skills` | Public fork | Cloudflare agent skills and MCP documentation. | Reference only; no KRAL runtime connector |

## Findings that affect the integration plan

1. The only active KRAL Android/backend target identified is `Gpt-asistan`.
2. No separate Google Drive, Vertex AI, Google Cloud, or Gemini connector repository was found in the 20-repository inventory.
3. `benim-uygulamam` contains a PROJECT OMEGA baseline, but its own scope file explicitly says Google Cloud and Drive are not authorized/provisioned and forbids treating external credentials as available.
4. `rish-mcp` is a separate Android shell bridge. Shell execution is materially more privileged than a read-only connector and must remain disconnected until a separate capability/approval boundary and device-owner authorization are implemented.
5. `telefon-yedek/GPTMobile-v0.6.3.apk` was located by filename only. Its package, signer, hash, contents, and relationship to the current KRAL APK are not established by this inventory.

## Explicit limitations

- A public repository being visible through GitHub does not prove that its runtime, secrets, deployment, or external services are available.
- The GitHub connection used for this inventory does not expose secret values; no secret values were requested or read.
- The inventory does not establish the user's Google Cloud project membership, Drive permissions, Vertex AI entitlement, or ChatGPT connector permissions.
- No repo outside `Gpt-asistan` was modified.
