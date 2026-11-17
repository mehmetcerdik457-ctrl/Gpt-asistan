# TinyFish × KRAL integration record — 18 November 2026

## Scope

This change adds a checked-in hosted MCP client configuration, local CLI setup helper, secret-safe offline preflight, bounded read-only browser runner, and integration documentation to the existing KRAL repository. It is based on the existing KRAL Gemini/OpenAI feature line; it does not create a new application.

## Included

- Current hosted Streamable-HTTP MCP endpoint configuration: `https://agent.tinyfish.ai/mcp`.
- CLI install/login/status helper. Installation and login require running the script on the user's own host.
- Offline preflight reporting Node/npm/CLI presence and only a boolean for `TINYFISH_API_KEY`.
- Explicit metered-run gate for a read-only browser runner (HTTPS-only, strict mode, max 10 steps and 60 seconds).
- Guidance for wallet metering.
- Explicit separation between hosted Gemma API access and actual local inference.

## Not claimed / not done

- No API key or secret value was read, created, changed, printed, or committed.
- No user's local phone/computer or Termux shell was accessed; CLI installation and sign-in have not been executed on the user's machine.
- No paid TinyFish agent, browser session, monitor, dataset, or Deep Research operation was executed.
- No TinyFish JSON-RPC proxy endpoint was added to the KRAL backend. The checked-in MCP configuration is for external MCP clients.
- No local Ollama/llama.cpp runtime was installed or connected end-to-end.
- No Android physical-device test or live Gemini/OpenAI/TinyFish provider call was performed by this change.
- No PR merge or `main` update was performed.

## Required acceptance after local setup

1. Run `python scripts/tinyfish_preflight.py` and verify sanitized output.
2. Run `bash scripts/tinyfish_setup.sh --install` only on the target host.
3. Run `bash scripts/tinyfish_setup.sh --login` and complete authentication in the provider's own flow.
4. Run `bash scripts/tinyfish_setup.sh --status` and confirm local authentication.
5. Configure the remote MCP endpoint in the intended MCP client; review client config changes before accepting.
6. Only after confirming the actual wallet balance and an explicit per-task spend ceiling, run the bounded read-only runner on an authorized HTTPS page.
