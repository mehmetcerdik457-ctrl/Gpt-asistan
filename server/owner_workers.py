"""Bounded local read-only worker batches behind the existing dual-P256 gateway.

This is not a remote agent launcher. No model, shell, network, tools, GitHub
write, or auto-approval path is present. At most four local threads run at once.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import time

MAX_LOGICAL_SLOTS = 50
MAX_PARALLEL = 4
_ID = re.compile(r"W(?:0[1-9]|[1-4][0-9]|50)\Z")
_ALLOWED = {"status", "memory.search", "history.recent", "models.cached"}


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != {"tasks", "max_parallel"}:
        raise ValueError("WORKER_FIELDS_INVALID")
    tasks = payload["tasks"]
    parallel = payload["max_parallel"]
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_LOGICAL_SLOTS:
        raise ValueError("WORKER_COUNT_INVALID")
    if type(parallel) is not int or not 1 <= parallel <= MAX_PARALLEL:
        raise ValueError("WORKER_PARALLEL_INVALID")
    used = set()
    for job in tasks:
        if not isinstance(job, dict) or set(job) != {"id", "kind", "args"}:
            raise ValueError("WORKER_JOB_INVALID")
        ident, kind, args = job["id"], job["kind"], job["args"]
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in used:
            raise ValueError("WORKER_ID_INVALID")
        used.add(ident)
        if not isinstance(kind, str) or kind not in _ALLOWED or not isinstance(args, dict):
            raise ValueError("WORKER_CAPABILITY_DENIED")
        if kind in ("status", "models.cached") and args:
            raise ValueError("WORKER_ARGS_DENIED")
        if kind == "history.recent":
            if set(args) != {"limit"} or type(args["limit"]) is not int or not 1 <= args["limit"] <= 5:
                raise ValueError("WORKER_HISTORY_ARGS_INVALID")
        if kind == "memory.search":
            if (set(args) != {"query", "limit"} or not isinstance(args["query"], str)
                    or not 1 <= len(args["query"]) <= 200
                    or type(args["limit"]) is not int or not 1 <= args["limit"] <= 10):
                raise ValueError("WORKER_MEMORY_ARGS_INVALID")
    return tasks, parallel


def _execute(gateway, job):
    try:
        kind, args = job["kind"], job["args"]
        if kind == "status":
            answer = {"scope": "local-owner-reads", "external_execution": False}
        elif kind == "memory.search":
            answer = {"memories": gateway.store.recall(args["query"], limit=args["limit"])}
        elif kind == "history.recent":
            answer = {"messages": gateway.store.history(limit=args["limit"])}
        elif kind == "models.cached":
            now = time.time()
            with gateway.lock:
                answer = {"models": [
                    {"id": m[0]["id"], "provider": m[0]["provider"]}
                    for m in gateway.models.values()
                    if 0 <= now - m[0]["verified_at"] < 900
                ]}
        else:
            # Defense in depth even if a caller bypasses validate().
            return {"id": job["id"], "status": "DENIED"}
        return {"id": job["id"], "status": "COMPLETED_LOCAL_READ", "result": answer}
    except Exception:
        # No exception text: SQLite and errors may contain private paths/data.
        return {"id": job["id"], "status": "BLOCKED_LOCAL_READ"}


def run_batch(gateway, payload):
    tasks, parallel = validate(payload)  # Whole-batch validation before any work.
    canonical = json.dumps(tasks, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    def bounded_execute(job):
        slots = getattr(gateway, "execution_slots", None)
        if slots is None:
            return _execute(gateway, job)
        with slots:
            return _execute(gateway, job)

    with ThreadPoolExecutor(max_workers=min(parallel, len(tasks))) as pool:
        results = list(pool.map(bounded_execute, tasks))
    return {
        "mode": "SIGNED_OWNER_READ_ONLY_LOCAL",
        "task_sha256": digest,
        "logical_worker_slots": MAX_LOGICAL_SLOTS,
        "executed_tasks": len(results),
        "parallel_limit": parallel,
        "provider_calls": 0,
        "external_actions": 0,
        "automatic_approvals": 0,
        "results": results,
    }
