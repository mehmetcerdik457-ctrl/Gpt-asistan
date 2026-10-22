"""Explicit opt-in Cloudflare Workers AI adapter. No hidden fallback or live claim."""
import json
import os
import re
import time
import urllib.error
import urllib.request

from .gateway import Denied, NoRedirect
from .owner_gateway_provider import normalized_messages

ACCT = re.compile(r"[a-f0-9]{32}\Z")
MODEL = re.compile(r"@cf/[a-z0-9][a-z0-9._-]{0,79}/[a-z0-9][a-z0-9._-]{0,119}\Z")
MAX_BODY = 131072


class CloudflareWorkersAIProvider:
    name = "cloudflare_workers_ai"

    def __init__(self, environ=None):
        self.env = os.environ if environ is None else environ

    def configured(self):
        e = self.env
        a, m, t = (e.get(k, "") for k in (
            "KRAL_CLOUDFLARE_ACCOUNT_ID", "KRAL_CLOUDFLARE_MODEL",
            "KRAL_CLOUDFLARE_API_TOKEN"))
        return (e.get("KRAL_CLOUDFLARE_COST_APPROVED") == "YES"
                and isinstance(a, str) and ACCT.fullmatch(a) is not None
                and isinstance(m, str) and MODEL.fullmatch(m) is not None
                and isinstance(t, str) and 16 <= len(t) <= 2048
                and t.isascii() and t.isprintable()
                and not any(c.isspace() for c in t))

    def candidates(self):
        if not self.configured():
            raise Denied("CLOUDFLARE_NOT_CONFIGURED", 503)
        return (self.env["KRAL_CLOUDFLARE_MODEL"],)

    def reply(self, model, message, *, probe=False):
        if not self.configured():
            raise Denied("CLOUDFLARE_NOT_CONFIGURED", 503)
        if model != self.env["KRAL_CLOUDFLARE_MODEL"]:
            raise Denied("CLOUDFLARE_MODEL_DENIED", 403)
        messages = normalized_messages(message)
        url = ("https://api.cloudflare.com/client/v4/accounts/"
               + self.env["KRAL_CLOUDFLARE_ACCOUNT_ID"] + "/ai/run/" + model)
        raw = json.dumps({"messages": messages, "stream": False,
                          "max_tokens": 64 if probe else 512},
                         ensure_ascii=False, separators=(",", ":")).encode()
        req = urllib.request.Request(url, data=raw, method="POST", headers={
            "Authorization": "Bearer " + self.env["KRAL_CLOUDFLARE_API_TOKEN"],
            "Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": "kral-workers-ai/1.0"})
        started = time.monotonic()
        try:
            with urllib.request.build_opener(NoRedirect()).open(
                    req, timeout=10 if probe else 30) as resp:
                if resp.status != 200 or resp.headers.get_content_type() != "application/json":
                    raise Denied("CLOUDFLARE_HTTP_FAILURE", 502)
                body = resp.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise Denied("CLOUDFLARE_RESPONSE_OVERSIZE", 502)
            data = json.loads(body)
            if (not isinstance(data, dict) or data.get("success") is not True
                    or data.get("errors", []) != [] or not isinstance(data.get("result"), dict)):
                raise Denied("CLOUDFLARE_RESPONSE_INVALID", 502)
            answer = data["result"].get("response")
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 16000:
                raise Denied("CLOUDFLARE_RESPONSE_INVALID", 502)
            # Workers AI API does not echo model identity; this is the pinned URL route.
            return answer, model, max(0, round((time.monotonic() - started) * 1000))
        except urllib.error.HTTPError as e:
            code = e.code
            e.close()  # Upstream bodies might include secrets; never forward.
            reason = ("CLOUDFLARE_AUTH_DENIED" if code in (401, 403) else
                      "CLOUDFLARE_RATE_OR_QUOTA" if code == 429 else "CLOUDFLARE_HTTP_FAILURE")
            raise Denied(reason, 502) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise Denied("CLOUDFLARE_UNAVAILABLE", 502) from None
        except (ValueError, TypeError, KeyError, AttributeError):
            raise Denied("CLOUDFLARE_RESPONSE_INVALID", 502) from None
