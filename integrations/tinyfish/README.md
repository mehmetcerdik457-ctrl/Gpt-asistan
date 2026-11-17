# TinyFish bridge for KRAL

This directory contains client-side configuration for the hosted TinyFish MCP service. It does not embed an API key and does not start an automation run.

## What is already connected

- The ChatGPT TinyFish connector is available in this workspace and can perform account-scoped Search, Fetch, and browser-agent operations.
- The KRAL backend feature line has Owner/device authenticated routes and OpenAI plus Gemini/Gemma provider adapters.
- This directory adds the external MCP client configuration and local CLI bootstrap instructions. It does not provision credentials, change wallet settings, or create a new cloud account.

## MCP / JSON-RPC client

The current hosted Streamable-HTTP MCP endpoint is configured in `mcp.json`:

```json
{
  "mcpServers": {
    "tinyfish": {
      "url": "https://agent.tinyfish.ai/mcp"
    }
  }
}
```

Use this remote MCP entry in an MCP-compatible client that supports remote HTTP MCP servers. MCP carries JSON-RPC messages; it is not a general-purpose unauthenticated JSON-RPC endpoint. The hosted service may prompt the user to authenticate on first use.

For clients that require a different configuration shape, copy the endpoint only into that client's official remote-MCP server setting. Do not invent a local proxy URL and do not put an API key in a checked-in JSON file.

## CLI setup

The official CLI package is `@tiny-fish/cli`. The currently published package requires Node.js 24 or newer.

1. Check the environment without sending a request:
   `python scripts/tinyfish_preflight.py`
2. Install the CLI on the machine that will run it:
   `bash scripts/tinyfish_setup.sh --install`
3. Start the official interactive account login locally:
   `bash scripts/tinyfish_setup.sh --login`
4. Confirm authentication locally:
   `bash scripts/tinyfish_setup.sh --status`
5. To let the CLI detect compatible local agent clients, review the proposed config changes before running:
   `npx -y @tiny-fish/cli@latest connect`

The setup script does not perform a browser run, paid research task, fetch, or monitor. Login may open the provider's authentication flow. Never paste a password, API key, browser cookie, or recovery code into chat.

If you prefer an environment variable, set `TINYFISH_API_KEY` in the private runtime environment. Do not add its value to this repository, Android resources, command-line arguments, logs, screenshots, or model prompts. The preflight script reports only whether the variable is present; it never prints or hashes the value.

## Metering and wallet safety

TinyFish automation and browser time can be metered. Do not run an agent task, create a monitor, or start Deep Research just to test authentication. First check the current wallet and the task's price model. Use a read-only, narrowly scoped request only after confirming the live balance and spend limit.

The wallet value is not stored in this repository. Auto-reload is a dashboard/account setting and must be checked from the live account; this integration does not enable it.

## Bounded read-only browser runner

A guarded runner is included at `scripts/tinyfish_agent_readonly.sh`. It requires an explicit billing acknowledgement, HTTPS URL, a locally authenticated CLI, strict mode, and short step/time ceilings:

```bash
bash scripts/tinyfish_agent_readonly.sh --confirm-metered-run \
  https://example.com "Read the page title and main heading"
```

Defaults are five steps and 30 seconds; the script caps configuration at ten steps and 60 seconds. These limits reduce scope but do not make an automation run free. The goal is augmented with instructions not to sign in, click controls, submit forms, buy, delete, publish, change settings, or modify records. Use only on sites you own or are authorized to inspect.

## Current boundaries

- No TinyFish API key was read, generated, rotated, or provisioned by this change.
- No external CLI was installed on the user's phone or computer by this change; the scripts must be run on that host.
- No paid browser task, monitor, dataset, or Deep Research job was started.
- The MCP endpoint is a client configuration; the KRAL server does not yet proxy arbitrary TinyFish JSON-RPC calls. A future server-side bridge must enforce Owner authentication, tool allowlists, per-task budget limits, idempotency, audit records, and explicit approval before billable actions.
- This does not grant blanket control over websites or accounts and does not bypass service billing, sign-in, or access controls.
