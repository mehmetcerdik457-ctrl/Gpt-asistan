"""Evidence-first inventory of AI engines and bridges discovered in public repos.

This module never calls a provider, reads secret values into output, or infers
live availability from a code path or environment variable alone.
"""
from __future__ import annotations

import os
from typing import Mapping

CATALOG = (
    {
        "id": "openai-responses",
        "kind": "hosted-model-api",
        "name": "OpenAI Responses API",
        "repo": "mehmetcerdik457-ctrl/Gpt-asistan",
        "ref": "integration/kral-asistan-20261020",
        "path": "server/gateway.py",
        "evidence": "provider implementation exists",
        "live_tested": False,
        "blocker": "No live provider call was performed for this inventory",
    },
    {
        "id": "android-compatible-endpoint",
        "kind": "hosted-compatible-api",
        "name": "Android OpenAI-compatible HTTPS endpoint",
        "repo": "mehmetcerdik457-ctrl/Gpt-asistan",
        "ref": "integration/kral-asistan-20261020",
        "path": "app/src/main/java/com/example/gptasistan/ModelGateway.kt",
        "evidence": "client transport exists; endpoint is user-configured",
        "live_tested": False,
        "blocker": "Device-side endpoint and credentials are not verified by repository CI",
    },
    {
        "id": "owner-gateway",
        "kind": "hosted-compatible-api",
        "name": "Owner-controlled OpenAI-compatible gateway",
        "repo": "mehmetcerdik457-ctrl/Gpt-asistan",
        "ref": "integration/cihat-github-task-bridge-20261021",
        "path": "server/owner_gateway_provider.py",
        "evidence": "adapter exists on the task-bridge integration branch",
        "live_tested": False,
        "blocker": "Owner gateway URL, token and model authorization not verified",
    },
    {
        "id": "omega-openai",
        "kind": "hosted-model-api",
        "name": "OMEGA existing OpenAI backend",
        "repo": "mehmetcerdik457-ctrl/benim-uygulamam",
        "ref": "main",
        "path": "backend/server.py",
        "evidence": "backend calls OpenAI if configured; not a local model runtime",
        "live_tested": False,
        "blocker": "Provider configuration and live call not verified",
    },
    {
        "id": "openai-agents-sdk",
        "kind": "agent-framework",
        "name": "OpenAI Agents SDK framework",
        "repo": "mehmetcerdik457-ctrl/openai-agents-python",
        "ref": "main",
        "path": "README.md",
        "evidence": "SDK/framework source is present; this is not a provisioned model",
        "live_tested": False,
        "blocker": "No runtime, credentials or agent task execution proven by repo presence",
    },
    {
        "id": "legacy-cihat-apk",
        "kind": "legacy-artifact",
        "name": "Legacy CİHAT/GPTMobile APK candidate",
        "repo": "mehmetcerdik457-ctrl/telefon-yedek",
        "ref": "main",
        "path": "GPTMobile-v0.6.3.apk",
        "evidence": "public APK artifact is listed; binary/backend not analyzed here",
        "live_tested": False,
        "blocker": "APK internals and its remote model service are unverified",
    },
    {
        "id": "rish-mcp",
        "kind": "device-tool-bridge",
        "name": "rish-mcp Android shell MCP bridge",
        "repo": "mehmetcerdik457-ctrl/rish-mcp",
        "ref": "master",
        "path": "README.md",
        "evidence": "MCP/Android device bridge source exists; not a model engine",
        "live_tested": False,
        "blocker": "Relay/device pairing and an attached AI client are not verified",
    },
    {
        "id": "google-gemini-vertex",
        "kind": "hosted-model-api",
        "name": "Google Gemini / Vertex AI",
        "repo": None,
        "ref": None,
        "path": None,
        "evidence": "no verified implementation found in the inspected repo trees/search",
        "live_tested": False,
        "blocker": "No code/configuration or authorized live endpoint found",
    },
    {
        "id": "local-ollama",
        "kind": "local-model-runtime",
        "name": "Ollama / local model weights",
        "repo": None,
        "ref": None,
        "path": None,
        "evidence": "no runtime config, model weights or serving endpoint verified",
        "live_tested": False,
        "blocker": "No owner machine/runtime is connected to this GitHub-only environment",
    },
    {
        "id": "ztn-gpt",
        "kind": "unknown-engine",
        "name": "ZTN GPT",
        "repo": None,
        "ref": None,
        "path": None,
        "evidence": "no verified matching repository path or adapter found in the accessible inventory",
        "live_tested": False,
        "blocker": "Need a discoverable repository/artifact or provider endpoint authorization",
    },
)

def inventory(environ: Mapping[str, str] | None = None) -> list[dict]:
    """Return public evidence and presence booleans only; never return secret values."""
    env = os.environ if environ is None else environ
    result = []
    for item in CATALOG:
        row = dict(item)
        if row["id"] == "openai-responses":
            row["configuration_present"] = bool(env.get("OPENAI_API_KEY", "").strip())
            row["model_allowlist_present"] = bool(env.get("OPENAI_ALLOWED_MODELS", "").strip())
        elif row["id"] == "owner-gateway":
            row["configuration_present"] = all(
                bool(env.get(key, "").strip()) for key in (
                    "KRAL_OWNER_GATEWAY_URL", "KRAL_OWNER_GATEWAY_HOST",
                    "KRAL_OWNER_GATEWAY_TOKEN", "KRAL_OWNER_GATEWAY_MODEL",
                )
            )
        else:
            row["configuration_present"] = None
        # Configuration is not a health check. Keep this false until a separately
        # authorized probe records a model ID, timestamp, and redacted result.
        row["live_tested"] = False
        result.append(row)
    return result
