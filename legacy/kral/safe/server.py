"""Fail-closed, single-owner HTTP transport for the existing Kral AI runtime.

Bind to loopback by default. For phone access put this service behind a TLS
terminating proxy and restrict access to the proxy's private network.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from assistant import ask_model

def run_fleet(prompt, task):
    from fleet import load_config, run
    path = os.environ.get("KRAL_FLEET_CONFIG")
    if not path:
        raise RuntimeError("fleet_not_configured")
    report = run(load_config(path), prompt, task)
    if not report.get("answer"):
        raise RuntimeError("fleet_failed")
    return report["answer"], "fleet", report.get("coordinator", "unknown")


MAX_REQUEST_BYTES = 16_384
MAX_RESPONSE_BYTES = 256_000


class OwnerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class OwnerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Neither owner tokens nor task texts belong in access logs.
        pass

    def respond(self, code, body):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if len(raw) > MAX_RESPONSE_BYTES:
            raw = b'{"error":"response_too_large"}'
            code = 502
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"status": "alive"})
        else:
            self.respond(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/v1/ask":
            self.respond(404, {"error": "not_found"})
            return
        bearer = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.owner_token
        if not hmac.compare_digest(bearer, expected):
            self.respond(401, {"error": "unauthorized"})
            return
        if self.headers.get("Transfer-Encoding"):
            self.respond(400, {"error": "chunked_not_supported"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            content_length = -1
        if not 0 < content_length <= MAX_REQUEST_BYTES:
            self.respond(413, {"error": "invalid_body_size"})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self.respond(415, {"error": "json_required"})
            return
        try:
            body = json.loads(self.rfile.read(content_length))
        except (ValueError, UnicodeError):
            self.respond(400, {"error": "invalid_json"})
            return
        if (not isinstance(body, dict) or "prompt" not in body
                or set(body) - {"prompt", "mode", "task"}):
            self.respond(400, {"error": "prompt_required"})
            return
        mode = body.get("mode", "single")
        task = body.get("task", "general")
        if mode not in ("single", "fleet") or task not in ("general", "code", "research", "writing"):
            self.respond(400, {"error": "invalid_route"})
            return
        if "prompt" not in body:
            self.respond(400, {"error": "prompt_required"})
            return
        prompt = body["prompt"]
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12_000:
            self.respond(400, {"error": "invalid_prompt"})
            return
        if not self.server.capacity.acquire(blocking=False):
            self.respond(429, {"error": "server_busy"})
            return
        try:
            answer, provider, model = (self.server.fleet_answer(prompt, task) if mode == "fleet"
                                       else self.server.answer(prompt))
            self.respond(200, {"answer": answer, "provider": provider, "model": model})
        except (RuntimeError, ValueError):
            # Provider error bodies and environment details are never exposed.
            self.respond(503, {"error": "model_unavailable"})
        except Exception:
            self.respond(500, {"error": "internal_error"})
        finally:
            self.server.capacity.release()


def make_server(host="127.0.0.1", port=8765, token=None, answer=None, remote=False, fleet_answer=None):
    key = token if token is not None else os.environ.get("KRAL_OWNER_TOKEN", "")
    if not isinstance(key, str) or len(key) < 32 or len(key) > 512:
        raise ValueError("KRAL_OWNER_TOKEN must be a strong 32-512 character secret")
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("invalid_port")
    if host not in ("127.0.0.1", "::1", "localhost") and not remote:
        raise ValueError("remote_bind_requires_explicit_opt_in")
    httpd = OwnerHTTPServer((host, port), OwnerHandler)
    httpd.owner_token = key
    httpd.answer = answer or ask_model
    httpd.fleet_answer = fleet_answer or run_fleet
    httpd.capacity = BoundedSemaphore(4)
    return httpd


def main():
    parser = argparse.ArgumentParser(description="Authenticated Kral owner API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--allow-remote-bind", action="store_true")
    args = parser.parse_args()
    try:
        server = make_server(args.host, args.port, remote=args.allow_remote_bind)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        print("OWNER_API=LISTENING (HTTP; use TLS proxy for remote clients)", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
