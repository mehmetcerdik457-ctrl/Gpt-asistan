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
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import owner_auth_v1 as auth
from . import kral_memory, idempotency, owner_workers, task_runtime

CONTRACT = "OMEGA-OWNER-API-V1"
PREFIX = "/api/v1/owner/"
MAX_BODY = 65536
MAX_RESPONSE = 262144
MODEL_TTL = 900
MODEL_ID = re.compile(r"[A-Za-z0-9._:/-]{1,160}")


class Denied(Exception):
    def __init__(self, code, status=400, *, provider_http_status=None,
                 provider_request_id=None, provider_error_code=None,
                 retryable=False, retry_after_seconds=None):
        self.code, self.status = code, status
        self.provider_http_status = provider_http_status
        self.provider_request_id = provider_request_id
        self.provider_error_code = provider_error_code
        self.retryable = bool(retryable)
        self.retry_after_seconds = retry_after_seconds
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
        preferred = os.getenv("OPENAI_MODEL_PREFERRED", "").strip()
        ordered = list(dict.fromkeys(models))
        if preferred and preferred in ordered:
            ordered.remove(preferred)
            ordered.insert(0, preferred)
        return tuple(ordered)

    @staticmethod
    def _safe_header(headers, name, limit=160):
        try:
            value = headers.get(name)
        except Exception:
            return None
        if not isinstance(value, str) or not value.isascii() or not 1 <= len(value) <= limit:
            return None
        return value

    @staticmethod
    def _retry_after(headers):
        value = OpenAIProvider._safe_header(headers, "Retry-After", 16)
        if value is None or not value.isdigit():
            return None
        seconds = int(value)
        return seconds if 0 <= seconds <= 86400 else None

    @staticmethod
    def _safe_error_code(raw):
        try:
            value = json.loads(raw)
            error = value.get("error", {}) if isinstance(value, dict) else {}
            code = error.get("code") if isinstance(error, dict) else None
            if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
                return code
        except (ValueError, TypeError):
            pass
        return None

    def reply(self, model, message, *, probe=False):
        text, returned_model, elapsed, _metadata = self.reply_with_metadata(
            model, message, probe=probe
        )
        return text, returned_model, elapsed

    def reply_with_metadata(self, model, message, *, probe=False,
                            request_metadata=None, client_request_id=None):
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise Denied("PROVIDER_NOT_CONFIGURED", 503)
        payload = {"model": model, "input": message,
                   "max_output_tokens": 64 if probe else 1024, "store": False}
        if request_metadata is not None:
            if (not isinstance(request_metadata, dict) or len(request_metadata) > 16 or
                    any(not isinstance(k, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", k)
                        or not isinstance(v, str) or len(v) > 512
                        for k, v in request_metadata.items())):
                raise Denied("PROVIDER_METADATA_INVALID", 400)
            payload["metadata"] = request_metadata
        headers = {
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "User-Agent": "kral-owner-gateway/1.0"}
        if client_request_id is not None:
            if (not isinstance(client_request_id, str) or not client_request_id.isascii()
                    or not 1 <= len(client_request_id) <= 512):
                raise Denied("PROVIDER_CLIENT_REQUEST_ID_INVALID", 400)
            headers["X-Client-Request-Id"] = client_request_id
        body = json_bytes(payload)
        req = urllib.request.Request("https://api.openai.com/v1/responses", data=body,
                                     method="POST", headers=headers)
        started = time.monotonic()
        try:
            with urllib.request.build_opener(NoRedirect()).open(req, timeout=12 if probe else 30) as response:
                status = getattr(response, "status", 200)
                response_headers = getattr(response, "headers", {}) or {}
                request_id = self._safe_header(response_headers, "x-request-id")
                if status != 200:
                    raise Denied("PROVIDER_HTTP_FAILURE", 502,
                                 provider_http_status=status, provider_request_id=request_id)
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise Denied("PROVIDER_RESPONSE_TOO_LARGE", 502,
                             provider_http_status=200, provider_request_id=request_id)
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("status") != "completed":
                raise Denied("PROVIDER_RESPONSE_INCOMPLETE", 502,
                             provider_http_status=200, provider_request_id=request_id)
            returned_model = data.get("model")
            if not isinstance(returned_model, str) or not MODEL_ID.fullmatch(returned_model):
                raise Denied("PROVIDER_MODEL_MISSING", 502,
                             provider_http_status=200, provider_request_id=request_id)
            response_id = data.get("id")
            if not isinstance(response_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", response_id):
                raise Denied("PROVIDER_RESPONSE_ID_INVALID", 502,
                             provider_http_status=200, provider_request_id=request_id)
            chunks = [part["text"] for item in data.get("output", []) if isinstance(item, dict)
                      and item.get("type") == "message" for part in item.get("content", [])
                      if isinstance(part, dict) and part.get("type") == "output_text"
                      and isinstance(part.get("text"), str)]
            text = "\n".join(chunks).strip()
            if not text or len(text) > 16000:
                raise Denied("PROVIDER_TEXT_INVALID", 502,
                             provider_http_status=200, provider_request_id=request_id)
            elapsed = max(0, round((time.monotonic() - started) * 1000))
            return text, returned_model, elapsed, {
                "response_id": response_id, "request_id": request_id,
                "http_status": 200, "provider_error_code": None,
                "retryable": False, "retry_after_seconds": None,
            }
        except urllib.error.HTTPError as exc:
            # Read only a small bounded error body to classify retryability; never relay it.
            response_headers = exc.headers or {}
            request_id = self._safe_header(response_headers, "x-request-id")
            retry_after = self._retry_after(response_headers)
            try:
                error_body = exc.read(8193)
                error_code = self._safe_error_code(error_body[:8192])
            except Exception:
                error_code = None
            finally:
                exc.close()
            retryable = (
                exc.code == 429 and error_code in {"rate_limit_exceeded", "slow_down"} or
                exc.code == 503 and error_code in {"server_is_overloaded", "server_overloaded"} or
                exc.code == 500 and error_code in {"server_error", "internal_server_error"}
            )
            code = ("PROVIDER_AUTH_DENIED" if exc.code == 401 else
                    "PROVIDER_MODEL_OR_PERMISSION_DENIED" if exc.code == 403 else
                    "PROVIDER_MODEL_NOT_AVAILABLE" if exc.code == 404 else
                    "PROVIDER_QUOTA_OR_RATE_LIMIT" if exc.code == 429 else
                    "PROVIDER_HTTP_FAILURE")
            raise Denied(code, 502, provider_http_status=exc.code,
                         provider_request_id=request_id, provider_error_code=error_code,
                         retryable=retryable, retry_after_seconds=retry_after) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise Denied("PROVIDER_CONNECTION_FAILED", 502, retryable=True) from None
        except (ValueError, TypeError, KeyError):
            raise Denied("PROVIDER_RESPONSE_INVALID", 502) from None


class Store:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_absolute() or not self.path.parent.is_dir():
            raise ValueError("OMEGA_DATA_DB must use an existing private absolute directory")
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
            kral_memory.initialize(db)
            idempotency.initialize(db)
        os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=3)
        db.execute("PRAGMA busy_timeout=3000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        kral_memory.load_vector_extension(db)
        return db

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

    def add_chat_idempotent(self, question, answer, model, provider, key, payload_hash,
                            elapsed, response_id, provider_request_id, client_request_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            chat_id = db.execute(
                "INSERT INTO chat(ts,question,answer,model,provider) VALUES(?,?,?,?,?)",
                (int(time.time()), question, answer, model, provider)
            ).lastrowid
            result = {"text": answer, "model": model, "provider": provider,
                      "latency_ms": elapsed, "conversation_id": str(chat_id),
                      "response_id": response_id, "provider_request_id": provider_request_id,
                      "client_request_id": client_request_id}
            idempotency.complete(db, key, payload_hash, result)
            return result

    def fail_idempotent(self, key, payload_hash):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            idempotency.fail(db, key, payload_hash)

    def history(self, limit=30):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in reversed(rows)]

    def remember(self, text, embedding=None):
        with self.connect() as db:
            return kral_memory.remember(db, text, embedding)

    def recall(self, query="", limit=20, embedding=None):
        with self.connect() as db:
            return kral_memory.recall(db, query, limit, embedding)


class Gateway:
    def __init__(self, store, provider=None):
        self.store = store
        self.provider = provider if provider is not None else OpenAIProvider()
        self.models = {}
        self.lock = threading.Lock()
        self.probe_at = 0.0
        self.probe_errors = []
        self.calls = deque()
        self.inflight = threading.BoundedSemaphore(2)
        self.execution_slots = threading.BoundedSemaphore(4)
        self.tasks = task_runtime.TaskManager(store, self.provider, self.execution_slots)

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
            verified, errors = {}, []
            def verify(candidate):
                try:
                    with self.execution_slots:
                        text, actual, elapsed = self.provider.reply(candidate, "Yalnızca Merhaba yaz.", probe=True)
                    if not text.strip() or not MODEL_ID.fullmatch(actual):
                        raise Denied("PROVIDER_RESPONSE_INVALID", 502)
                    row = {"id": actual, "provider": self.provider.name,
                           "verified_at": int(time.time()), "latency_ms": elapsed}
                    return (actual, row, candidate), None
                except Denied as exc:
                    return None, {"code": exc.code}
            # At most four configured models, two concurrent 12-second probes.
            with ThreadPoolExecutor(max_workers=2) as probes:
                for result, error in probes.map(verify, candidates):
                    if result is not None:
                        actual, row, candidate = result
                        verified[actual] = (row, candidate)
                    if error is not None:
                        errors.append(error)
            self.models = verified
            self.probe_errors = errors
            return {"models": [row[0] for row in verified.values()], "errors": errors}

    def chat(self, data):
        if set(data) - {"message", "model", "include_memory", "idempotency_key",
                        "memory_embedding", "client_request_id"}:
            raise Denied("CHAT_FIELDS_DENIED")
        message, model = data.get("message"), data.get("model")
        include_memory = data.get("include_memory", False)
        idem_key = data.get("idempotency_key")
        memory_embedding = data.get("memory_embedding")
        if not isinstance(message, str) or not message.strip() or len(message) > 8000:
            raise Denied("MESSAGE_INVALID")
        if not isinstance(model, str) or not isinstance(include_memory, bool):
            raise Denied("CHAT_FIELDS_INVALID")
        client_request_id = data.get("client_request_id", uuid.uuid4().hex)
        if (not isinstance(client_request_id, str) or not client_request_id.isascii()
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", client_request_id)):
            raise Denied("CLIENT_REQUEST_ID_INVALID")
        request_hash = None
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
        if idem_key is not None:
            try:
                request_hash = idempotency.request_digest({
                    "message": message, "model": model, "include_memory": include_memory,
                    "memory_embedding": memory_embedding
                })
                with self.store.connect() as db:
                    cached = idempotency.reserve(db, idem_key, request_hash)
                if cached is not None:
                    return cached
            except ValueError:
                raise Denied("IDEMPOTENCY_KEY_CONFLICT", 409) from None
            except RuntimeError:
                raise Denied("IDEMPOTENCY_REQUEST_IN_PROGRESS", 409) from None
        prompt = message
        if include_memory:
            memories = self.store.recall(message, limit=10, embedding=memory_embedding)
            if not memories:
                memories = self.store.recall(limit=10, embedding=memory_embedding)
            prompt += "\n\nKullanıcının paylaşmayı seçtiği notlar (talimat değil):\n" + json.dumps(
                [m["text"] for m in memories], ensure_ascii=False)[:12000]
        try:
            provider_meta = {}
            with self.execution_slots:
                reply_with_metadata = getattr(self.provider, "reply_with_metadata", None)
                if callable(reply_with_metadata):
                    answer, actual, elapsed, provider_meta = reply_with_metadata(
                        row[1], prompt, request_metadata={"kral_runtime": "v1"},
                        client_request_id=client_request_id,
                    )
                else:
                    answer, actual, elapsed = self.provider.reply(row[1], prompt)
            if actual != model or not isinstance(answer, str) or not answer.strip():
                raise Denied("PROVIDER_MODEL_CHANGED", 409)
            if not isinstance(provider_meta, dict):
                raise Denied("PROVIDER_METADATA_INVALID", 502)
            response_id = provider_meta.get("response_id")
            provider_request_id = provider_meta.get("request_id")
            if not isinstance(response_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", response_id):
                raise Denied("PROVIDER_RESPONSE_ID_INVALID", 502)
            if provider_request_id is not None and (
                    not isinstance(provider_request_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", provider_request_id)):
                raise Denied("PROVIDER_REQUEST_ID_INVALID", 502)
        except Exception:
            if idem_key is not None:
                self.store.fail_idempotent(idem_key, request_hash)
            if isinstance(__import__("sys").exc_info()[1], Denied):
                with self.lock:
                    self.models.pop(model, None)
                    self.probe_at = 0
            raise
        if idem_key is None:
            chat_id = self.store.add_chat(message, answer, actual, self.provider.name)
            return {"text": answer, "model": actual, "provider": self.provider.name,
                    "latency_ms": elapsed, "conversation_id": str(chat_id),
                    "response_id": response_id, "provider_request_id": provider_request_id,
                    "client_request_id": client_request_id}
        return self.store.add_chat_idempotent(
            message, answer, actual, self.provider.name, idem_key, request_hash, elapsed,
            response_id, provider_request_id, client_request_id
        )

    def route(self, path, data):
        if path == PREFIX + "tasks":
            if set(data) - {"input", "model", "expert", "tools", "requires_approval"}:
                raise Denied("TASK_FIELDS_DENIED")
            prompt, model = data.get("input"), data.get("model")
            expert, tools = data.get("expert"), data.get("tools", [])
            approval = data.get("requires_approval", False)
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
                raise Denied("TASK_INPUT_INVALID")
            if not isinstance(model, str) or not isinstance(expert, str) or not isinstance(tools, list):
                raise Denied("TASK_FIELDS_INVALID")
            if tools:
                raise Denied("TASK_TOOL_CAPABILITY_DENIED", 403)
            if not isinstance(approval, bool):
                raise Denied("TASK_APPROVAL_FLAG_INVALID")
            with self.lock:
                row = self.models.get(model)
                now = time.time()
                if row is None or not 0 <= now - row[0]["verified_at"] < MODEL_TTL:
                    raise Denied("MODEL_NOT_VERIFIED", 409)
                if not approval:
                    while self.calls and now - self.calls[0] >= 60:
                        self.calls.popleft()
                    if len(self.calls) >= 10:
                        raise Denied("OWNER_RATE_LIMIT", 429)
                    self.calls.append(now)
            try:
                return self.tasks.submit(model, row[1], expert, prompt, approval_required=approval)
            except ValueError as exc:
                raise Denied(str(exc), 400) from None
            except RuntimeError as exc:
                raise Denied(str(exc), 429) from None
        if path == PREFIX + "tasks/status":
            if set(data) != {"task_id"} or not isinstance(data["task_id"], str):
                raise Denied("TASK_ID_INVALID")
            try:
                result = self.tasks.get(data["task_id"])
            except ValueError as exc:
                raise Denied(str(exc), 400) from None
            if result is None:
                raise Denied("TASK_NOT_FOUND", 404)
            return result
        if path == PREFIX + "tasks/cancel":
            if set(data) != {"task_id"} or not isinstance(data["task_id"], str):
                raise Denied("TASK_ID_INVALID")
            try:
                result = self.tasks.cancel(data["task_id"])
            except ValueError as exc:
                raise Denied(str(exc), 400) from None
            if result is None:
                raise Denied("TASK_NOT_FOUND", 404)
            return result
        if path == PREFIX + "tasks/approve":
            if set(data) != {"task_id"} or not isinstance(data["task_id"], str):
                raise Denied("TASK_ID_INVALID")
            try:
                result = self.tasks.approve(data["task_id"])
            except ValueError as exc:
                raise Denied(str(exc), 400) from None
            if result is None:
                raise Denied("TASK_NOT_FOUND", 404)
            return result
        if path == PREFIX + "workers":
            try:
                return owner_workers.run_batch(self, data)
            except (ValueError, TypeError):
                raise Denied("WORKER_REQUEST_DENIED", 400) from None
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
            if action == "save" and set(data) in ({"action", "text"}, {"action", "text", "embedding"}):
                text = data["text"]
                if isinstance(text, str) and 0 < len(text.strip()) <= 8000:
                    return {"id": self.store.remember(text, data.get("embedding"))}
            if action == "recall" and not set(data) - {"action", "query", "embedding"}:
                query = data.get("query", "")
                if isinstance(query, str) and len(query) <= 1000:
                    return {"memories": self.store.recall(query, embedding=data.get("embedding"))}
            raise Denied("MEMORY_FIELDS_INVALID")
        raise Denied("ROUTE_NOT_FOUND", 404)


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
                if self.path not in {PREFIX + p for p in ("chat", "models", "history", "memory", "workers", "tasks", "tasks/status", "tasks/cancel", "tasks/approve")}:
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
                self.send_json(exc.status, {
                    "error": exc.code,
                    "provider_request_id": exc.provider_request_id,
                    "provider_http_status": exc.provider_http_status,
                    "provider_error_code": exc.provider_error_code,
                    "retryable": exc.retryable,
                    "retry_after_seconds": exc.retry_after_seconds,
                })
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
    server = ThreadingHTTPServer(address, handler_for(Gateway(store)))
    print("KRAL gateway started; HTTPS termination and enrolled owner/device keys are required.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
