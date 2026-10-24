"""Optional owner-approved *single* GitHub Copilot issue dispatcher.

Default is DRY RUN. A live request requires a separate user-to-server OAuth/PAT
credential, explicit three switches and a verified safe base branch. GitHub App
installation and default GITHUB_TOKEN credentials are NOT valid for Copilot
assignment in many accounts; no bypass is attempted. Never auto-merges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from server import mission_control as mission

API_ROOT = "https://api.github.com/repos/"
BOT = "copilot-swe-agent[bot]"
BRANCH = re.compile(r"(?:integration|security)/[A-Za-z0-9._/-]{1,130}\Z")
SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|"
                    r"sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}|"
                    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                    r"https?://[^/\s]+:[^@/\s]+@)", re.I)
MARKER_PREFIX = "<!-- kral-owner-dispatch-v1:"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise mission.MissionRejected("DISPATCH_REDIRECT_DENIED")


def check_branch(value):
    if (not isinstance(value, str) or not BRANCH.fullmatch(value)
        or "//" in value or any(x in (".", "..") for x in value.split("/"))
        or value.endswith("/") or value.endswith(".")):
        raise mission.MissionRejected("SAFE_BRANCH_REQUIRED")
    return value


def proposal(manifest, repositories, task_id: str, branch: str):
    _, _, tasks = mission.validate_manifest(manifest, repositories)
    check_branch(branch)
    if task_id not in tasks:
        raise mission.MissionRejected("TASK_NOT_IN_MANIFEST")
    job = tasks[task_id]
    if job["depends_on"]:
        raise mission.MissionRejected("DEPENDENCY_NEEDS_LIVE_VERIFICATION")
    # GitHub issues are often PUBLIC. Never publish possible credentials.
    content = job["title"] + "\n" + job["description"]
    if SECRET.search(content):
        raise mission.MissionRejected("POSSIBLE_SECRET_IN_PUBLIC_ISSUE")
    # Content digest for deduplication without exposing full text in preview.
    digest = hashlib.sha256(json.dumps(job, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    marker = MARKER_PREFIX + digest + " -->"
    body = "\n".join([
        marker,
        "Owner-approved KRAL scoped coding task. Preserve original sources.",
        "Task: " + job["id"],
        "Requested expertise: " + job["role"],
        "Target repository: " + job["repo"],
        "Base branch: " + branch,
        "Allowed file scope: " + ", ".join(job["paths"]),
        "Instruction (untrusted task text):",
        job["description"],
        "",
        "Mandatory: create own work branch/PR; tests, commit SHA, CI logs and independent owner review.",
        "Do not touch main, merge, publish, change secrets, upload private data or start paid external services.",
        "If unavailable or unsure, stop and report BLOCKED. No fake PASS.",
    ])
    return {
        "repo": job["repo"],
        "id": job["id"],
        "role": job["role"],
        "base_branch": branch,
        "dedup_marker": marker,
        "issue_title": "[KRAL OWNER TASK " + job["id"] + "] " + job["title"],
        "issue_body": body,
        "api_request": {
            "title": "[KRAL OWNER TASK " + job["id"] + "] " + job["title"],
            "body": body,
            "assignees": [BOT],
            "agent_assignment": {
                "target_repo": job["repo"],
                "base_branch": branch,
                "custom_instructions": ("Work within file scope; test before PR, await Owner review. "
                                        "Requested expert profile: " + job["role"]),
                # We cannot assert the non-default-branch custom profile is
                # installed or selectable, so do not invent a custom_agent ID.
                "custom_agent": "",
                "model": "",
            },
        },
    }


def _request(repo: str, endpoint: str, token: str, method="GET", payload=None):
    if not isinstance(repo, str) or not re.fullmatch(
            r"mehmetcerdik457-ctrl/[A-Za-z0-9._-]{1,100}", repo):
        raise mission.MissionRejected("DISPATCH_REPO_INVALID")
    if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
        raise mission.MissionRejected("OWNER_TOKEN_MISSING")
    if (not isinstance(endpoint, str) or
        not (endpoint in ("issues", "issues?state=all&per_page=100")
             or endpoint.startswith("branches/"))):
        raise mission.MissionRejected("DISPATCH_ENDPOINT_INVALID")
    if endpoint.startswith("branches/"):
        check_branch(endpoint[len("branches/"):])
    if method not in ("GET", "POST") or (method == "POST" and endpoint != "issues"):
        raise mission.MissionRejected("DISPATCH_METHOD_DENIED")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    if (method == "GET" and data is not None) or (method == "POST" and data is None):
        raise mission.MissionRejected("DISPATCH_BODY_DENIED")
    req = urllib.request.Request(
        API_ROOT + repo + "/" + endpoint, data=data, method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "kral-owner-dispatch/1.0",
        })
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise mission.MissionRejected("DISPATCH_RESPONSE_TOO_LARGE")
        return json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        raise mission.MissionRejected("DISPATCH_GITHUB_API_FAILED") from None


def submit_one(scoped, token):
    # Caller already explicitly agreed to potentially billed Copilot work.
    # A single call can never start more than one issue/session.
    repo, branch, marker = scoped["repo"], scoped["base_branch"], scoped["dedup_marker"]
    found = _request(repo, "branches/" + branch, token)
    if not isinstance(found, dict) or found.get("name") != branch:
        raise mission.MissionRejected("SAFE_BRANCH_NOT_VERIFIED")
    issues = _request(repo, "issues?state=all&per_page=100", token)
    if not isinstance(issues, list) or len(issues) >= 100:
        raise mission.MissionRejected("DUPLICATE_CHECK_NOT_COMPLETE")
    for issue in issues:
        if isinstance(issue, dict) and marker in str(issue.get("body") or ""):
            raise mission.MissionRejected("TASK_ALREADY_SUBMITTED")
    result = _request(repo, "issues", token, "POST", scoped["api_request"])
    if not isinstance(result, dict) or type(result.get("number")) is not int:
        raise mission.MissionRejected("DISPATCH_CONFIRMATION_MISSING")
    # Issue creation is not proof that Copilot accepted or started a session.
    return {"status": "ISSUE_CREATED_AGENT_NOT_VERIFIED",
            "repository": repo, "issue_number": result["number"],
            "requires": "Check Copilot assignment/session/PR via live GitHub events."}


def main(argv=None):
    parser = argparse.ArgumentParser(description="One-task Copilot dispatch; default DRY_RUN.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--owner-approved", action="store_true")
    parser.add_argument("--public-issue-approved", action="store_true")
    args = parser.parse_args(argv)
    try:
        allowed = mission.validate_repository_inventory(
            mission.read_small_json(mission.REPO_INVENTORY, 16384))
        scoped = proposal(mission.read_small_json(args.manifest), allowed,
                          args.task, args.branch)
        if not args.execute:
            print(json.dumps({
                "status": "DRY_RUN_NOT_SUBMITTED",
                "task": scoped["id"], "role": scoped["role"], "repo": scoped["repo"],
                "branch": scoped["base_branch"],
                "copilot_custom_agent": "NOT_VERIFIED",
                "owner_approval_required": True,
            }, ensure_ascii=False))
            return 0
        if not (args.owner_approved and args.public_issue_approved):
            raise mission.MissionRejected("EXPLICIT_OWNER_APPROVAL_REQUIRED")
        # GitHub Actions token and GitHub App installation token are not an
        # acceptable substitute for user-to-server authorization.
        if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
            raise mission.MissionRejected("ACTIONS_TOKEN_NOT_ACCEPTED_FOR_AGENT_ASSIGNMENT")
        token = os.environ.get("KRAL_COPILOT_USER_TOKEN", "")
        if not token:
            raise mission.MissionRejected("USER_TO_SERVER_TOKEN_REQUIRED")
        print(json.dumps(submit_one(scoped, token), ensure_ascii=False))
        return 0
    except (mission.MissionRejected, OSError, TypeError, KeyError):
        # Never print a URL that could contain secrets or reflect untrusted
        # user-supplied text; codes only.
        print("KRAL_DISPATCH_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
