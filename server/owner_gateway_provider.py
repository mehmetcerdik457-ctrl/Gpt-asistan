"""Optional owner-controlled OpenAI-compatible HTTPS gateway adapter.

This is NOT a recovered API from CİHAT AI 3.2.1 or evidence that its models
are locally available. A separately authorized, HTTPS service is required.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .gateway import Denied, MODEL_ID, NoRedirect

MAX_UPSTREAM_BYTES = 131072
HOST_PATTERN = re.compile(
    r"(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


def valid_endpoint(url: str, allowed_host: str) -> bool:
    """Pinned hostname, HTTPS 443 and fixed path; no internal/IP literal targets."""
    if not isinstance(url, str) or not isinstance(allowed_host, str):
        return False
    if len(url) > 600 or not HOST_PATTERN.fullmatch(allowed_host):
        return False
    if allowed_host in ("localhost", "metadata.google.internal"):
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.netloc == allowed_host
            and parsed.hostname == allowed_host
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
            and parsed.path == "/v1/chat/completions"
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def normalized_messages(value):
    """No arbitrary roles/tools or malformed personal-memory structures."""
    if isinstance(value, str):
        if not value.strip() or len(value) > 12000:
            raise Denied("OWNER_GATEWAY_INPUT_DENIED", 400)
        return [{"role": "user", "content": value}]
    if not isinstance(value, list) or not 1 <= len(value) <= 9:
        raise Denied("OWNER_GATEWAY_INPUT_DENIED", 400)
    total = 0
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"role", "content"}:
            raise Denied("OWNER_GATEWAY_INPUT_DENIED", 400)
        role, content = item["role"], item["content"]
        if role not in ("user", "assistant") or not isinstance(content, str):
            raise Denied("OWNER_GATEWAY_INPUT_DENIED", 400)
        if not content.strip() or len(content) > 12000:
            raise Denied("OWNER_GATEWAY_INPUT_DENIED", 400)
        total += len(content)
        if total > 12000:
            raise Denied("OWNER_GATEWAY_INPUT_DENIED", 400)
        result.append({"role": role, "content": content})
    return result


class OwnerGatewayProvider:
    """Only an owner-provisioned independent, compatible API can be used."""
    name = "owner_gateway"

    def __init__(self, environ=None):
        self.env = os.environ if environ is None else environ

    def configured(self):
        e = self.env
        endpoint = e.get("KRAL_OWNER_GATEWAY_URL", "")
        host = e.get("KRAL_OWNER_GATEWAY_HOST", "")
        token = e.get("KRAL_OWNER_GATEWAY_TOKEN", "")
        model = e.get("KRAL_OWNER_GATEWAY_MODEL", "")
        return (
            valid_endpoint(endpoint, host)
            and isinstance(token, str) and 16 <= len(token) <= 2048
            and "\r" not in token and "\n" not in token
            and isinstance(model, str) and MODEL_ID.fullmatch(model) is not None
        )

    def candidates(self):
        if not self.configured():
            raise Denied("OWNER_GATEWAY_NOT_CONFIGURED", 503)
        return (self.env["KRAL_OWNER_GATEWAY_MODEL"],)

    def reply(self, model, message, *, probe=False):
        if not self.configured():
            raise Denied("OWNER_GATEWAY_NOT_CONFIGURED", 503)
        if model != self.env["KRAL_OWNER_GATEWAY_MODEL"]:
            raise Denied("OWNER_GATEWAY_MODEL_DENIED", 403)
        messages = normalized_messages(message)
        raw = json.dumps({
            "model": model, "stream": False,
            "messages": messages, "max_tokens": 64 if probe else 1024,
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            self.env["KRAL_OWNER_GATEWAY_URL"], data=raw, method="POST",
            headers={
                "Authorization": "Bearer " + self.env["KRAL_OWNER_GATEWAY_TOKEN"],
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "kral-owner-gateway-adapter/1.0",
            }
        )
        start = time.monotonic()
        try:
            with urllib.request.build_opener(NoRedirect()).open(
                req, timeout=10 if probe else 30
            ) as response:
                if response.status != 200:
                    raise Denied("OWNER_GATEWAY_HTTP_ERROR", 502)
                if response.headers.get_content_type() != "application/json":
                    raise Denied("OWNER_GATEWAY_CONTENT_TYPE", 502)
                payload = response.read(MAX_UPSTREAM_BYTES + 1)
            if len(payload) > MAX_UPSTREAM_BYTES:
                raise Denied("OWNER_GATEWAY_RESPONSE_TOO_LARGE", 502)
            data = json.loads(payload)
            returned = data["model"]
            choices = data["choices"]
            answer = choices[0]["message"]["content"]
            if (returned != model or not isinstance(answer, str)
                or not answer.strip() or len(answer) > 16000):
                raise Denied("OWNER_GATEWAY_RESPONSE_INVALID", 502)
            return answer, returned, round((time.monotonic() - start) * 1000)
        except urllib.error.HTTPError as error:
            error.close()
            raise Denied("OWNER_GATEWAY_HTTP_ERROR", 502) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise Denied("OWNER_GATEWAY_UNAVAILABLE", 502) from None
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise Denied("OWNER_GATEWAY_RESPONSE_INVALID", 502) from None


def provider_from_env():
    """Explicit selection: no fallback to another provider after any failure."""
    mode = os.environ.get("KRAL_PROVIDER_MODE", "openai")
    if mode == "openai":
        from .gateway import OpenAIProvider
        return OpenAIProvider()
    if mode == "owner_gateway":
        return OwnerGatewayProvider()
    if mode == "cloudflare_workers_ai":
        from .cloudflare_workers_ai_provider import CloudflareWorkersAIProvider
        return CloudflareWorkersAIProvider()
    if mode == "multi_verified":
        from .multi_verified_provider import VerifiedProviderPool
        return VerifiedProviderPool()
    raise Denied("PROVIDER_MODE_INVALID", 503)
