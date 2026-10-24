"""KRAL mission planner: 50 logical slots, up to 100 scoped, auditable tasks.

OFFLINE ONLY: This module never starts models, spends credits, writes to
GitHub, merges PRs, runs code, or declares work complete. External actions
require a separate owner-authorized dispatch and independently checked CI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPOSITORY_OWNER = "mehmetcerdik457-ctrl"
MAX_TASKS = 100
MAX_WORKERS = 50
MAX_PARALLEL = 4
MANIFEST_KEYS = {"schema", "owner", "worker_slots", "max_parallel", "tasks"}
TASK_KEYS = {"id", "repo", "role", "title", "description", "depends_on", "paths"}
ROLES = (
    "github-master-ai", "chief-engineer", "android-engineer",
    "ai-ml-engineer", "mcp-engineer", "cloud-engineer",
    "ci-cd-engineer", "test-engineer", "security-auditor",
    "code-reviewer", "apk-forensic", "release-engineer",
)
REPO_INVENTORY = Path(__file__).resolve().parents[1] / "missions" / "repo_inventory.json"
ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}\Z")
REPO_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,100}\Z")
PATH_PART = re.compile(r"[A-Za-z0-9._@+-]{1,120}\Z")


class MissionRejected(ValueError):
    """No arbitrary task commands are ever executed."""


def _integer(value, minimum: int, maximum: int, name: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MissionRejected(name + "_INVALID")
    return value


def _text(value, maximum: int, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise MissionRejected(name + "_INVALID")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise MissionRejected(name + "_CONTROL_CHARACTER")
    return value.strip()


def validate_repository_inventory(data) -> frozenset[str]:
    if not isinstance(data, dict) or set(data) != {"owner", "repositories"}:
        raise MissionRejected("REPO_INVENTORY_FORMAT")
    if data["owner"] != REPOSITORY_OWNER:
        raise MissionRejected("REPO_OWNER_DENIED")
    names = data["repositories"]
    if not isinstance(names, list) or not 1 <= len(names) <= 100:
        raise MissionRejected("REPO_INVENTORY_LENGTH")
    if any(not isinstance(n, str) or not REPO_PATTERN.fullmatch(n) for n in names):
        raise MissionRejected("REPO_NAME_INVALID")
    if len(names) != len(set(names)):
        raise MissionRejected("REPO_DUPLICATE")
    return frozenset(REPOSITORY_OWNER + "/" + n for n in names)


def validate_path(value) -> str:
    if not isinstance(value, str) or not value or len(value) > 300:
        raise MissionRejected("PATH_INVALID")
    raw = value.rstrip("/")
    if not raw or value.startswith("/") or "\\" in value or ":" in value:
        raise MissionRejected("PATH_INVALID")
    if any(not PATH_PART.fullmatch(x) or x in (".", "..") for x in raw.split("/")):
        raise MissionRejected("PATH_TRAVERSAL_DENIED")
    return value


def validate_manifest(data, allowed_repositories: frozenset[str]):
    if not isinstance(data, dict) or set(data) != MANIFEST_KEYS:
        raise MissionRejected("MANIFEST_FIELDS_INVALID")
    if data["schema"] != 1 or type(data["schema"]) is not int:
        raise MissionRejected("MANIFEST_SCHEMA_DENIED")
    if data["owner"] != REPOSITORY_OWNER:
        raise MissionRejected("MANIFEST_OWNER_DENIED")
    workers = _integer(data["worker_slots"], 1, MAX_WORKERS, "WORKER_SLOTS")
    parallel = _integer(data["max_parallel"], 1, min(workers, MAX_PARALLEL), "PARALLEL_LIMIT")
    tasks = data["tasks"]
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
        raise MissionRejected("TASK_COUNT_INVALID")
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict) or set(task) != TASK_KEYS:
            raise MissionRejected("TASK_FIELDS_INVALID")
        identifier = task["id"]
        if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
            raise MissionRejected("TASK_ID_INVALID")
        if identifier in by_id:
            raise MissionRejected("TASK_ID_DUPLICATE")
        repo = task["repo"]
        if not isinstance(repo, str) or repo not in allowed_repositories:
            raise MissionRejected("TARGET_REPOSITORY_NOT_IN_INVENTORY")
        if task["role"] not in ROLES:
            raise MissionRejected("AGENT_ROLE_NOT_APPROVED")
        _text(task["title"], 120, "TASK_TITLE")
        _text(task["description"], 2000, "TASK_DESCRIPTION")
        paths = task["paths"]
        if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
            raise MissionRejected("TASK_PATHS_INVALID")
        for path in paths:
            validate_path(path)
        dependencies = task["depends_on"]
        if not isinstance(dependencies, list) or len(dependencies) > MAX_TASKS:
            raise MissionRejected("TASK_DEPENDENCIES_INVALID")
        if any(not isinstance(x, str) or not ID_PATTERN.fullmatch(x) for x in dependencies):
            raise MissionRejected("DEPENDENCY_ID_INVALID")
        if len(set(dependencies)) != len(dependencies) or identifier in dependencies:
            raise MissionRejected("DEPENDENCY_DUPLICATE_OR_SELF")
        by_id[identifier] = task
    for task in tasks:
        for dependency in task["depends_on"]:
            if dependency not in by_id:
                raise MissionRejected("DEPENDENCY_MISSING")
    return workers, parallel, by_id


def make_plan(manifest, allowed_repositories):
    """Construct hypothetical waves. Scheduled != executed or verified.

    The repo-wide lock intentionally prevents concurrent edits to one repo,
    even for nonoverlapping paths; dependency prerequisites never run in the
    same proposed wave. Actual dispatch must wait for external acceptance.
    """
    workers, parallel, remaining = validate_manifest(manifest, allowed_repositories)
    prior_waves = set()
    waves = []
    planned_count = 0
    while remaining:
        candidates = sorted(
            (item for item in remaining.values()
             if set(item["depends_on"]) <= prior_waves),
            key=lambda item: item["id"],
        )
        chosen = []
        used_repositories = set()
        for task in candidates:
            if task["repo"] in used_repositories:
                continue
            worker = 1 + ((planned_count + len(chosen)) % workers)
            chosen.append({
                "task": task["id"],
                "repo": task["repo"],
                "role": task["role"],
                "worker_slot": f"worker-{worker:02d}",
                "requires_owner_dispatch": True,
                "status": "NOT_EXECUTED",
                "supervisor": "PENDING_VERIFIED_PR_AND_CI",
            })
            used_repositories.add(task["repo"])
            if len(chosen) == parallel:
                break
        if not chosen:
            raise MissionRejected("TASK_DEPENDENCY_CYCLE")
        waves.append({"wave": len(waves) + 1, "assignments": chosen})
        planned_count += len(chosen)
        for job in chosen:
            prior_waves.add(job["task"])
            del remaining[job["task"]]
    return {
        "schema": 1,
        "type": "OFFLINE_DISPATCH_BLUEPRINT",
        "execution": "NOT_STARTED",
        "owner": REPOSITORY_OWNER,
        "worker_slots": workers,
        "parallel_cap": parallel,
        "task_count": planned_count,
        "waves": waves,
        "caution": "50 logical worker slots are not 50 live AI sessions. No issue, PR, model, or tool call was made.",
    }


def read_small_json(path: Path, limit: int = 262144):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise MissionRejected("INPUT_FILE_DENIED")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError, OSError):
        raise MissionRejected("INPUT_JSON_DENIED") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Plan 1-100 KRAL jobs, without dispatching AI or modifying repositories.")
    parser.add_argument("manifest", type=Path, help="Owner-authored JSON mission; no shell commands are run.")
    parser.add_argument("--out", type=Path, help="Optional local JSON report path; no GitHub upload")
    args = parser.parse_args(argv)
    try:
        repos = validate_repository_inventory(read_small_json(REPO_INVENTORY, 16384))
        plan = make_plan(read_small_json(args.manifest), repos)
        encoded = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        if args.out is None:
            print(encoded, end="")
        else:
            if args.out.is_symlink() or not args.out.parent.is_dir():
                raise MissionRejected("REPORT_DESTINATION_DENIED")
            args.out.write_text(encoded, encoding="utf-8")
            print(json.dumps({"status": plan["execution"], "report": str(args.out),
                              "tasks": plan["task_count"], "waves": len(plan["waves"])}))
    except (MissionRejected, OSError) as exc:
        print("MISSION_BLOCKED: " + (str(exc) if isinstance(exc, MissionRejected) else "IO_ERROR"), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
