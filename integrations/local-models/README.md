# Open-weight and local model integration status

## Already present in the KRAL feature line

The existing KRAL server feature line includes deterministic OpenAI and Google Gemini/Gemma provider routing. Gemini/Gemma credentials are server-only, model IDs are explicitly allowlisted, provider failures do not silently fall back across providers, and requests use `store: false`.

Gemma is an open-weight model family, but using Gemma through Google's hosted Gemini API is **not** the same as running an open model locally on the phone or private server.

## Local inference is not yet wired end-to-end

The Android `ModelGateway` currently accepts HTTPS OpenAI-compatible endpoints and rejects plain HTTP endpoints. Therefore a default local Ollama endpoint such as `http://127.0.0.1:11434/v1` must not be entered into the current Android setting and described as working. No local model runtime is considered configured until a concrete runtime adapter, isolation boundary, endpoint policy, and device/server test exist.

A future local-runtime adapter should:
- bind to loopback or a private container network only;
- reject public destinations, redirects, DNS rebinding, and arbitrary user-supplied URLs;
- keep model files and prompts local where possible;
- use explicit model allowlists, request/response size caps, timeouts, and task concurrency limits;
- avoid sending secrets, chat history, or private memory unless the Owner approves the exact scope;
- emit a local health/result record without claiming a live model response until an actual inference succeeds.

## Candidate local runtimes

Ollama and llama.cpp are candidate runtimes, not configured dependencies in this branch. Select the target device (Android/Termux, a private Linux host, or a container host) before wiring either runtime. The runtime installation and local model download can require substantial storage, memory, bandwidth, and compute.

Do not put model/API credentials in Android source, Git, this documentation, or an MCP configuration file.
