"""Single-owner HTTP service. Deploy behind HTTPS with a persistent private volume.

Provider access is server-only. Every protected request needs both enrolled EC
signatures and a fresh nonce; an email, device identifier or health response is
never authentication. No private OMEGA runtime is represented by this service.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import owner_auth_v1 as auth
from .secure_sqlite import secure_sqlite_file
from .source_owner_tool import inspect_source, SourceInspectionDenied

CONTRACT = "OMEGA-OWNER-API-V1"
PREFIX = "/api/v1/owner/"
MAX_BODY = 65536
MAX_RESPONSE = 262144
MAX_MEMORY_ROWS = 1000
MAX_MEMORY_BYTES = 4 * 1024 * 1024
MAX_CONTEXT_TURNS = 3
MAX_CONTEXT_CHARS = 12000
MODEL_TTL = 900
MODEL_ID = re.compile(r"[A-Za-z0-9._:/-]{1,160}")
# Cloudflare Workers AI uses an @cf/vendor/model route, unlike the ordinary
# OpenAI-compatible model names. Never allow this syntax for other providers.
CLOUDFLARE_MODEL_ID = re.compile(
    r"@cf/[a-z0-9][a-z0-9._-]{0,79}/[a-z0-9][a-z0-9._-]{0,119}\Z"
)


def valid_discovered_model_id(model, provider):
    if not isinstance(model, str):
        return False
    if provider == "cloudflare_workers_ai":
        return len(model) <= 200 and CLOUDFLARE_MODEL_ID.fullmatch(model) is not None
    return MODEL_ID.fullmatch(model) is not None


class Denied(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Denied("PROVIDER_REDIRECT_DENIED", 502)


class OpenAIProvider:
    """Fixed official endpoint; arbitrary upstream URLs are not accepted."""
    name = "openai"

    def configured(self):
        return bool(os.getenv("OPENAI_API_KEY", "").strip())

    def candidates(self):
        models = [m.strip() for m in os.getenv("OPENAI_ALLOWED_MODELS", "").split(",") if m.strip()]
        if len(models) > 4 or any(not MODEL_ID.fullmatch(m) for m in models):
            raise Denied("MODEL_CONFIGURATION_INVALID", 503)
        return tuple(dict.fromkeys(models))

    def reply(self, model, message, *, probe=False):
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise Denied("PROVIDER_NOT_CONFIGURED", 503)
        body = json_bytes({"model": model, "input": message,
                           "max_output_tokens": 64 if probe else 1024, "store": False})
        req = urllib.request.Request("https://api.openai.com/v1/responses", data=body, method="POST", headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "User-Agent": "kral-owner-gateway/1.0"})
        started = time.monotonic()
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=12 if probe else 30) as response:
                if response.status != 200:
                    raise Denied("PROVIDER_HTTP_FAILURE", 502)
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise Denied("PROVIDER_RESPONSE_TOO_LARGE", 502)
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("status") != "completed":
                raise Denied("PROVIDER_RESPONSE_INCOMPLETE", 502)
            returned_model = data.get("model")
            if not isinstance(returned_model, str) or not MODEL_ID.fullmatch(returned_model):
                raise Denied("PROVIDER_MODEL_MISSING", 502)
            chunks = [part["text"] for item in data.get("output", []) if isinstance(item, dict)
                      and item.get("type") == "message" for part in item.get("content", [])
                      if isinstance(part, dict) and part.get("type") == "output_text"
                      and isinstance(part.get("text"), str)]
            text = "\n".join(chunks).strip()
            if not text or len(text) > 16000:
                raise Denied("PROVIDER_TEXT_INVALID", 502)
            return text, returned_model, max(0, round((time.monotonic() - started) * 1000))
        except urllib.error.HTTPError as exc:
            # Error bodies may contain upstream request information. Never relay them.
            exc.close()
            code = "PROVIDER_AUTH_DENIED" if exc.code in (401, 403) else (
                "PROVIDER_QUOTA_OR_RATE_LIMIT" if exc.code == 429 else "PROVIDER_HTTP_FAILURE")
            raise Denied(code, 502) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise Denied("PROVIDER_CONNECTION_FAILED", 502) from None
        except (ValueError, TypeError, KeyError):
            raise Denied("PROVIDER_RESPONSE_INVALID", 502) from None


class Store:
    def __init__(self, path):
        self.path = Path(secure_sqlite_file(path))
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chat (
                    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, question TEXT NOT NULL,
                    answer TEXT NOT NULL, model TEXT NOT NULL, provider TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, text TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS owner_binding (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    owner_id TEXT NOT NULL, public_key_sha256 TEXT NOT NULL);
            """)

    def connect(self):
        return sqlite3.connect(str(self.path), timeout=3)

    def bind_owner(self, owner_id, public_key_sha256):
        """An identity configuration change cannot silently inherit another owner DB."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner_id,public_key_sha256 FROM owner_binding WHERE singleton=1").fetchone()
            if row is None:
                populated = db.execute("SELECT EXISTS(SELECT 1 FROM chat) OR EXISTS(SELECT 1 FROM memory)").fetchone()[0]
                if populated:
                    raise Denied("UNBOUND_EXISTING_STORE_REQUIRES_OWNER_MIGRATION", 503)
                db.execute("INSERT INTO owner_binding VALUES(1,?,?)", (owner_id, public_key_sha256))
            elif row != (owner_id, public_key_sha256):
                raise Denied("PERSISTENT_STORE_OWNER_MISMATCH", 403)

    def add_chat(self, question, answer, model, provider):
        with self.connect() as db:
            return db.execute("INSERT INTO chat(ts,question,answer,model,provider) VALUES(?,?,?,?,?)",
                              (int(time.time()), question, answer, model, provider)).lastrowid

    def history(self, limit=30):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in reversed(rows)]

    def recent_context(self):
        """Return a bounded chronological context; newest turns take precedence."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT question,answer FROM chat ORDER BY id DESC LIMIT ?", (MAX_CONTEXT_TURNS,)
            ).fetchall()
        reverse_messages = []
        remaining = MAX_CONTEXT_CHARS
        for question, answer in rows:
            # Do not create a partial turn when fewer than two characters remain.
            if remaining < 2:
                break
            question, answer = question.strip(), answer.strip()
            question_budget = min(len(question), remaining // 2)
            answer_budget = min(len(answer), remaining - question_budget)
            question_budget = min(len(question), remaining - answer_budget)
            # A zero-sized slice (text[-0:]) returns the entire private message.
            # Both messages must fit the remaining context budget.
            if not question_budget or not answer_budget:
                break

            def tail(text, budget):
                if budget <= 0:
                    return ""
                if len(text) <= budget:
                    return text
                return "…" + text[-(budget - 1):] if budget > 1 else text[-budget:]

            user_content = tail(question, question_budget)
            assistant_content = tail(answer, answer_budget)
            reverse_messages.append({"role": "assistant", "content": assistant_content})
            reverse_messages.append({"role": "user", "content": user_content})
            remaining -= len(user_content) + len(assistant_content)
            if remaining <= 0:
                break
        return list(reversed(reverse_messages))

    def remember(self, text):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row_count, byte_count = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(length(CAST(text AS BLOB))), 0) FROM memory"
            ).fetchone()
            text_bytes = len(text.encode("utf-8"))
            if row_count >= MAX_MEMORY_ROWS or byte_count + text_bytes > MAX_MEMORY_BYTES:
                raise Denied("MEMORY_QUOTA_EXCEEDED", 507)
            return db.execute("INSERT INTO memory(ts,text) VALUES(?,?)", (int(time.time()), text)).lastrowid

    def recall(self, query="", limit=20):
        # instr uses a literal search; SQL metacharacters and LIKE wildcards stay data.
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM memory WHERE instr(text,?)>0 ORDER BY id DESC LIMIT ?",
                              (query, limit)).fetchall()
            return [dict(row) for row in reversed(rows)]


class Gateway:
    def __init__(self, store, provider=None):
        self.store = store
        if provider is None:
            from .owner_gateway_provider import provider_from_env
            provider = provider_from_env()
        self.provider = provider
        self.models = {}
        self.lock = threading.Lock()
        self.probe_at = 0.0
        self.probe_errors = []
        self.calls = deque()
        self.inflight = threading.BoundedSemaphore(2)

    def verified_models(self):
        now = time.time()
        with self.lock:
            if not self.provider.configured():
                self.models.clear()
                return {"models": [], "errors": [{"code": "PROVIDER_NOT_CONFIGURED"}]}
            if now - self.probe_at < 60:
                return {"models": [row[0] for row in self.models.values() if 0 <= now - row[0]["verified_at"] < MODEL_TTL],
                        "errors": self.probe_errors}
            candidates = self.provider.candidates()
            if not candidates:
                self.models.clear()
                return {"models": [], "errors": [{"code": "MODEL_ALLOWLIST_EMPTY"}]}
            self.probe_at = now
            verified, errors, collision_ids = {}, [], set()
            def verify(candidate):
                try:
                    text, actual, elapsed = self.provider.reply(candidate, "Yalnızca Merhaba yaz.", probe=True)
                    # In an opt-in pool each verified model retains the REAL
                    # provider's identity, never the synthetic pool label.
                    provider_name = (self.provider.provider_name_for(candidate)
                                     if hasattr(self.provider, "provider_name_for")
                                     else self.provider.name)
                    if not text.strip() or not valid_discovered_model_id(actual, provider_name):
                        raise Denied("PROVIDER_RESPONSE_INVALID", 502)
                    row = {"id": actual, "provider": provider_name,
                           "verified_at": int(time.time()), "latency_ms": elapsed}
                    return (actual, row, candidate), None
                except Denied as exc:
                    return None, {"code": exc.code}
            # At most four configured models, two concurrent 12-second probes.
            with ThreadPoolExecutor(max_workers=2) as probes:
                for result, error in probes.map(verify, candidates):
                    if result is not None:
                        actual, row, candidate = result
                        # The Android contract selects by unqualified model
                        # ID. Never silently overwrite one real provider with
                        # another provider reporting the same ID.
                        if actual in collision_ids or actual in verified:
                            verified.pop(actual, None)
                            collision_ids.add(actual)
                            errors.append({"code": "MODEL_PROVIDER_COLLISION"})
                        else:
                            verified[actual] = (row, candidate)
                    if error is not None:
                        errors.append(error)
            self.models = verified
            self.probe_errors = errors
            return {"models": [row[0] for row in verified.values()], "errors": errors}

    def chat(self, data):
        if set(data) - {"message", "model", "include_memory", "include_history"}:
            raise Denied("CHAT_FIELDS_DENIED")
        message, model = data.get("message"), data.get("model")
        include_memory = data.get("include_memory", False)
        include_history = data.get("include_history", False)
        if not isinstance(message, str) or not message.strip() or len(message) > 8000:
            raise Denied("MESSAGE_INVALID")
        if not isinstance(model, str) or not isinstance(include_memory, bool) or not isinstance(include_history, bool):
            raise Denied("CHAT_FIELDS_INVALID")
        with self.lock:
            row = self.models.get(model)
            now = time.time()
            if row is None or not 0 <= now - row[0]["verified_at"] < MODEL_TTL:
                raise Denied("MODEL_NOT_VERIFIED", 409)
            while self.calls and now - self.calls[0] >= 60:
                self.calls.popleft()
            if len(self.calls) >= 10:
                raise Denied("OWNER_RATE_LIMIT", 429)
            self.calls.append(now)
        prompt = self.store.recent_context() if include_history else []
        if include_memory:
            memories = self.store.recall(limit=10)
            prompt.append({"role": "user", "content": "Kullanıcının paylaşmayı seçtiği notlar:\n" + json.dumps(
                [m["text"] for m in memories], ensure_ascii=False)[:12000]})
        if include_history or include_memory:
            prompt.append({"role": "user", "content": message})
        else:
            prompt = message
        try:
            answer, actual, elapsed = self.provider.reply(row[1], prompt)
            if actual != model or not answer.strip():
                raise Denied("PROVIDER_MODEL_CHANGED", 409)
        except Denied:
            with self.lock:
                self.models.pop(model, None)
                self.probe_at = 0
            raise
        # Preserve the actual selected provider in durable history and the
        # Android reply contract; never label multiple providers as a fake one.
        verified_provider = row[0]["provider"]
        chat_id = self.store.add_chat(message, answer, actual, verified_provider)
        return {"text": answer, "model": actual, "provider": verified_provider,
                "latency_ms": elapsed, "conversation_id": str(chat_id)}

    def inspect_owner_source(self, data):
        if set(data) != {"action", "source_id"} or data.get("action") != "inspect":
            raise Denied("SOURCE_FIELDS_DENIED", 400)
        try:
            return {"source": inspect_source(
                os.getenv("KRAL_SOURCE_ROOT", ""), data["source_id"])}
        except SourceInspectionDenied as exc:
            raise Denied(str(exc), 403 if str(exc).startswith("SOURCE_PATH") or
                         str(exc).startswith("SOURCE_LINK") or
                         str(exc).startswith("SOURCE_TYPE") else 400) from None

    def route(self, path, data):
        if path == PREFIX + "sources":
            return self.inspect_owner_source(data)
        if path == PREFIX + "models":
            if data:
                raise Denied("MODEL_FIELDS_DENIED")
            return self.verified_models()
        if path == PREFIX + "chat":
            return self.chat(data)
        if path == PREFIX + "history":
            limit = data.get("limit", 30)
            if set(data) - {"limit"} or type(limit) is not int or not 1 <= limit <= 100:
                raise Denied("HISTORY_FIELDS_INVALID")
            return {"messages": self.store.history(limit)}
        if path == PREFIX + "memory":
            action = data.get("action")
            if action == "save" and set(data) == {"action", "text"}:
                text = data["text"]
                if isinstance(text, str) and text.strip() and len(text) <= 8000:
                    return {"id": self.store.remember(text)}
            if action == "recall" and not set(data) - {"action", "query"}:
                query = data.get("query", "")
                if isinstance(query, str) and len(query) <= 1000:
                    return {"memories": self.store.recall(query)}
            raise Denied("MEMORY_FIELDS_INVALID")
        raise Denied("ROUTE_NOT_FOUND", 404)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Bound unauthenticated connections before they can allocate worker threads."""
    MAX_WORKERS = 16

    def __init__(self, server_address, RequestHandlerClass, *, max_workers=None, **kwargs):
        super().__init__(server_address, RequestHandlerClass, **kwargs)
        self.max_workers = self.MAX_WORKERS if max_workers is None else max_workers
        if self.max_workers < 1:
            raise ValueError("max_workers must be positive")
        self._worker_slots = threading.BoundedSemaphore(self.max_workers)

    def process_request(self, request, client_address):
        if not self._worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], OSError):
            return
        super().handle_error(request, client_address)


def handler_for(gateway):
    class Handler(BaseHTTPRequestHandler):
        server_version = "KralGateway/1.0"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            # Default HTTP logging may include request paths; no user input logged.
            pass

        def send_json(self, status, data):
            body = json_bytes({"contract": CONTRACT, **data})
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/health":
                self.send_json(200, {"status": "ok", "provider_verified": False,
                                     "authentication": "dual-p256-request-signature"})
            else:
                self.send_json(404, {"error": "ROUTE_NOT_FOUND"})

        def do_POST(self):
            acquired = False
            try:
                if self.path not in {PREFIX + p for p in ("chat", "models", "history", "memory", "sources")}:
                    raise Denied("ROUTE_NOT_FOUND", 404)
                if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                    raise Denied("BODY_LENGTH_REQUIRED", 411)
                content_type = self.headers.get_content_type()
                if content_type != "application/json":
                    raise Denied("JSON_REQUIRED", 415)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise Denied("BODY_TOO_LARGE", 413)
                if any(len(self.headers.get_all(name, [])) != 1 for name in auth.REQUIRED):
                    raise Denied("OWNER_AUTH_REQUIRED", 403)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise Denied("BODY_INCOMPLETE")
                allowed, reason = auth.authorize(self.headers, raw, "POST", self.path)
                if not allowed:
                    raise Denied(reason, 503 if reason == "OWNER_IDENTITY_NOT_PROVISIONED" else 403)
                owner_key = auth._decode(os.environ["OMEGA_OWNER_PUBLIC_DER_B64"])
                gateway.store.bind_owner(self.headers["X-Omega-Owner-Id"], hashlib.sha256(owner_key).hexdigest())
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise Denied("JSON_OBJECT_REQUIRED")
                acquired = gateway.inflight.acquire(blocking=False)
                if not acquired:
                    raise Denied("OWNER_REQUEST_BUSY", 429)
                result = gateway.route(self.path, data)
                self.send_json(200, result)
            except Denied as exc:
                self.send_json(exc.status, {"error": exc.code})
            except (ValueError, UnicodeError):
                self.send_json(400, {"error": "REQUEST_INVALID"})
            except sqlite3.Error:
                self.send_json(503, {"error": "PERSISTENT_STORE_UNAVAILABLE"})
            except Exception:
                self.send_json(500, {"error": "SERVER_REQUEST_FAILED"})
            finally:
                if acquired:
                    gateway.inflight.release()
                self.close_connection = True
    return Handler


def main():
    os.umask(0o077)
    store = Store(os.environ["OMEGA_DATA_DB"])
    address = (os.getenv("KRAL_BIND", "127.0.0.1"), int(os.getenv("PORT", "8080")))
    server = BoundedThreadingHTTPServer(address, handler_for(Gateway(store)))
    print("KRAL gateway started; HTTPS termination and enrolled owner/device keys are required.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
