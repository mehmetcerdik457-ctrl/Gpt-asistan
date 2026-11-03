"""Durable, owner-bound local tool proposals and single-use approvals.

Only the fixed local registry below is executable. No model output grants
authority, and no provider, shell, URL, or arbitrary callable can be dispatched.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import sqlite3
import time
from types import MappingProxyType
import uuid

from . import kral_memory


APPROVAL_TTL = 300
MAX_PENDING_TASKS = 50
_ID = re.compile(r"[a-f0-9]{32}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")


class ToolDenied(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class Capability:
    scope: str
    approval_class: str


CAPABILITIES = MappingProxyType({
    "status": Capability("local.status", "read_only"),
    "memory.save": Capability("local.memory", "owner_approval"),
})


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _actor(value):
    if (not isinstance(value, dict) or
            set(value) != {"owner_id", "device_id", "owner_key_sha256"} or
            not isinstance(value["owner_id"], str) or
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value["owner_id"]) or
            any(not isinstance(value[name], str) or not _SHA.fullmatch(value[name])
                for name in ("device_id", "owner_key_sha256"))):
        raise ToolDenied("TOOL_ACTOR_DENIED", 403)
    return dict(value)


def _capability(tool, arguments, scope):
    capability = CAPABILITIES.get(tool) if isinstance(tool, str) else None
    if capability is None:
        raise ToolDenied("TOOL_CAPABILITY_DENIED", 403)
    if scope != capability.scope:
        raise ToolDenied("TOOL_SCOPE_DENIED", 403)
    if not isinstance(arguments, dict):
        raise ToolDenied("TOOL_ARGUMENTS_INVALID")
    if tool == "status":
        if arguments:
            raise ToolDenied("TOOL_ARGUMENTS_INVALID")
    elif (set(arguments) != {"text"} or not isinstance(arguments["text"], str) or
          not arguments["text"].strip() or len(arguments["text"]) > 8000):
        raise ToolDenied("TOOL_ARGUMENTS_INVALID")
    return capability


class ToolTasks:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tool_tasks (
                    tool_task_id TEXT PRIMARY KEY,
                    proposal_json TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    approved_at INTEGER,
                    approved_by TEXT,
                    result_json TEXT,
                    tools_executed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS tool_task_audit (
                    id INTEGER PRIMARY KEY,
                    tool_task_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    at INTEGER NOT NULL,
                    actor_json TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tool_task_audit_task
                    ON tool_task_audit(tool_task_id, id);
            """)

    @staticmethod
    def _audit(db, task_id, event, now, actor, digest):
        db.execute(
            "INSERT INTO tool_task_audit(tool_task_id,event,at,actor_json,request_sha256) "
            "VALUES(?,?,?,?,?)", (task_id, event, now, _json(actor), digest))

    @staticmethod
    def _load(db, task_id):
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM tool_tasks WHERE tool_task_id=?", (task_id,)).fetchone()
        if row is None:
            raise ToolDenied("TOOL_TASK_NOT_FOUND", 404)
        proposal = json.loads(row["proposal_json"])
        if (not isinstance(proposal, dict) or
                set(proposal) != {"tool_task_id", "tool", "arguments", "scope", "actor",
                                  "approval_class", "created_at", "expires_at"} or
                hashlib.sha256(_json(proposal).encode("utf-8")).hexdigest() != row["request_sha256"] or
                proposal["tool_task_id"] != row["tool_task_id"] or
                proposal["created_at"] != row["created_at"] or
                proposal["expires_at"] != row["expires_at"]):
            raise ToolDenied("TOOL_PROPOSAL_INVALID", 409)
        capability = _capability(proposal["tool"], proposal["arguments"], proposal["scope"])
        _actor(proposal["actor"])
        if proposal["approval_class"] != capability.approval_class:
            raise ToolDenied("TOOL_PROPOSAL_INVALID", 409)
        return row, proposal

    def _lookup(self, db, data, actor):
        task_id, digest = data.get("tool_task_id"), data.get("request_sha256")
        if (not isinstance(task_id, str) or not _ID.fullmatch(task_id) or
                not isinstance(digest, str) or not _SHA.fullmatch(digest)):
            raise ToolDenied("TOOL_FIELDS_INVALID")
        row, proposal = self._load(db, task_id)
        if proposal["actor"] != actor:
            raise ToolDenied("TOOL_ACTOR_DENIED", 403)
        if row["request_sha256"] != digest:
            raise ToolDenied("TOOL_APPROVAL_MISMATCH", 403)
        return row, proposal

    def _expire(self, db, row, proposal, now):
        if row["status"] == "awaiting_approval" and now >= row["expires_at"]:
            db.execute("UPDATE tool_tasks SET status='expired' WHERE tool_task_id=?",
                       (row["tool_task_id"],))
            self._audit(db, row["tool_task_id"], "expired", now,
                        proposal["actor"], row["request_sha256"])
            return True
        return row["status"] == "expired"

    def _result(self, db, task_id):
        row, proposal = self._load(db, task_id)
        audit = [{"event": item["event"], "at": item["at"],
                  "actor": json.loads(item["actor_json"]),
                  "request_sha256": item["request_sha256"]}
                 for item in db.execute(
                     "SELECT * FROM tool_task_audit WHERE tool_task_id=? ORDER BY id", (task_id,))]
        return {**proposal, "request_sha256": row["request_sha256"], "status": row["status"],
                "result": json.loads(row["result_json"]) if row["result_json"] is not None else None,
                "approved_at": row["approved_at"],
                "approved_by": json.loads(row["approved_by"]) if row["approved_by"] else None,
                "tools_executed": row["tools_executed"], "external_actions": 0,
                "audit": audit}

    def submit(self, data, actor):
        actor = _actor(actor)
        if not isinstance(data, dict) or set(data) != {"tool", "arguments", "scope"}:
            raise ToolDenied("TOOL_FIELDS_INVALID")
        capability = _capability(data["tool"], data["arguments"], data["scope"])
        task_id = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = int(self.clock())
            # Round-trip the validated JSON so caller mutation cannot change an approval.
            proposal = json.loads(_json({"tool_task_id": task_id, **data, "actor": actor,
                                        "approval_class": capability.approval_class,
                                        "created_at": now, "expires_at": now + APPROVAL_TTL}))
            encoded = _json(proposal)
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            db.row_factory = sqlite3.Row
            expired = list(db.execute(
                "SELECT tool_task_id FROM tool_tasks WHERE status='awaiting_approval' AND expires_at<=?",
                (now,)))
            for item in expired:
                row, previous = self._load(db, item["tool_task_id"])
                self._expire(db, row, previous, now)
            if capability.approval_class == "owner_approval":
                pending = db.execute(
                    "SELECT COUNT(*) FROM tool_tasks WHERE status='awaiting_approval'").fetchone()[0]
                if pending >= MAX_PENDING_TASKS:
                    raise ToolDenied("TOOL_TASK_CAPACITY_REACHED", 429)
            status = "awaiting_approval" if capability.approval_class == "owner_approval" else "completed"
            db.execute(
                "INSERT INTO tool_tasks(tool_task_id,proposal_json,request_sha256,status,created_at,expires_at) "
                "VALUES(?,?,?,?,?,?)", (task_id, encoded, digest, status, now, now + APPROVAL_TTL))
            self._audit(db, task_id, "proposed", now, actor, digest)
            if status == "completed":
                result = {"scope": "local-status", "external_execution": False}
                db.execute("UPDATE tool_tasks SET result_json=?,tools_executed=1 WHERE tool_task_id=?",
                           (_json(result), task_id))
                self._audit(db, task_id, "completed", now, actor, digest)
            return self._result(db, task_id)

    def get(self, data, actor):
        actor = _actor(actor)
        if not isinstance(data, dict) or set(data) != {"tool_task_id", "request_sha256"}:
            raise ToolDenied("TOOL_FIELDS_INVALID")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, proposal = self._lookup(db, data, actor)
            self._expire(db, row, proposal, int(self.clock()))
            return self._result(db, row["tool_task_id"])

    def approve(self, data, actor):
        actor = _actor(actor)
        if (not isinstance(data, dict) or
                set(data) != {"tool_task_id", "request_sha256", "tool", "arguments", "scope"}):
            raise ToolDenied("TOOL_FIELDS_INVALID")
        expired = False
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, proposal = self._lookup(db, data, actor)
            if any(data[key] != proposal[key] for key in ("tool", "arguments", "scope")):
                raise ToolDenied("TOOL_APPROVAL_MISMATCH", 403)
            now = int(self.clock())
            expired = self._expire(db, row, proposal, now)
            if not expired:
                if row["status"] != "awaiting_approval":
                    raise ToolDenied("TOOL_TASK_NOT_PENDING", 409)
                # No callable, URL or model-supplied handler may cross this boundary.
                if proposal["tool"] != "memory.save" or proposal["approval_class"] != "owner_approval":
                    raise ToolDenied("TOOL_CAPABILITY_DENIED", 403)
                self._audit(db, row["tool_task_id"], "approved", now, actor, row["request_sha256"])
                memory_id = kral_memory.remember(db, proposal["arguments"]["text"])
                db.execute(
                    "UPDATE tool_tasks SET status='completed',approved_at=?,approved_by=?,result_json=?,"
                    "tools_executed=1 WHERE tool_task_id=?",
                    (now, _json(actor), _json({"id": memory_id}), row["tool_task_id"]))
                self._audit(db, row["tool_task_id"], "completed", now, actor, row["request_sha256"])
                result = self._result(db, row["tool_task_id"])
        if expired:
            # Raise after commit so expiration is durable, without any tool execution.
            raise ToolDenied("TOOL_TASK_EXPIRED", 409)
        return result

    def cancel(self, data, actor):
        actor = _actor(actor)
        if not isinstance(data, dict) or set(data) != {"tool_task_id", "request_sha256"}:
            raise ToolDenied("TOOL_FIELDS_INVALID")
        expired = False
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, proposal = self._lookup(db, data, actor)
            now = int(self.clock())
            expired = self._expire(db, row, proposal, now)
            if not expired:
                if row["status"] != "awaiting_approval":
                    raise ToolDenied("TOOL_TASK_NOT_PENDING", 409)
                db.execute("UPDATE tool_tasks SET status='cancelled' WHERE tool_task_id=?",
                           (row["tool_task_id"],))
                self._audit(db, row["tool_task_id"], "cancelled", now, actor, row["request_sha256"])
            result = self._result(db, row["tool_task_id"])
        if expired:
            raise ToolDenied("TOOL_TASK_EXPIRED", 409)
        return result
