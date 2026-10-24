"""KRAL read-only supervisor: verify *actual* PR and Actions run identity.

A successful CI run is not final acceptance. Only the human owner can merge.
No repository writes, no model calls, no shell, no access to secrets APIs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

from server import mission_control as mission

GITHUB_ROOT = "https://api.github.com/repos/"
SHA = re.compile(r"[0-9a-f]{40}\Z")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise mission.MissionRejected("REDIRECT_DENIED")


def evaluate(repo, pr_number, run_number, pr, run, allowlist):
    """Never infer merge approval from a CI pass or a Copilot message."""
    if not isinstance(repo, str) or repo not in allowlist:
        raise mission.MissionRejected("REPO_NOT_ALLOWLISTED")
    mission._integer(pr_number, 1, 100000000, "PR")
    mission._integer(run_number, 1, 1000000000000, "RUN")
    if not isinstance(pr, dict) or not isinstance(run, dict):
        raise mission.MissionRejected("API_RESPONSE_INVALID")
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    if not isinstance(head, dict) or not isinstance(base, dict):
        raise mission.MissionRejected("PR_STRUCTURE_INVALID")
    sha = head.get("sha")
    if (not isinstance(sha, str) or not SHA.fullmatch(sha)
        or (head.get("repo") or {}).get("full_name") != repo
        or (base.get("repo") or {}).get("full_name") != repo
        or type(pr.get("number")) is not int or pr["number"] != pr_number):
        raise mission.MissionRejected("PR_SOURCE_IDENTITY_DENIED")
    if (pr.get("state") != "open" or pr.get("merged_at") is not None
        or base.get("ref") == "main"):
        raise mission.MissionRejected("PR_BASE_OR_MERGE_DENIED")
    if ((run.get("repository") or {}).get("full_name") != repo
        or type(run.get("id")) is not int or run.get("id") != run_number
        or run.get("head_sha") != sha):
        raise mission.MissionRejected("CI_PROVENANCE_MISMATCH")
    if ((run.get("actor") or {}).get("login") != mission.REPOSITORY_OWNER):
        raise mission.MissionRejected("CI_NOT_OWNER_TRIGGERED")
    status = ("CI_PASS_AWAIT_OWNER_REVIEW"
              if run.get("status") == "completed" and run.get("conclusion") == "success"
              else "CI_NOT_VERIFIED")
    return {
        "repository": repo,
        "pr": pr_number,
        "run": run_number,
        "commit": sha,
        "status": status,
        "merge_approved": False,
        "claimed_work_completed": False,
        "required": "Human inspect PR changes, review test logs, security and dependency gates.",
        "evidence": "https://github.com/" + repo + "/actions/runs/" + str(run_number),
    }


def github_get(repo: str, resource: str, token: str):
    if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repo):
        raise mission.MissionRejected("INVALID_REPO")
    if not re.fullmatch(r"(?:pulls|actions/runs)/[1-9][0-9]*", resource):
        raise mission.MissionRejected("INVALID_ENDPOINT")
    if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
        raise mission.MissionRejected("TOKEN_MISSING")
    request = urllib.request.Request(
        GITHUB_ROOT + repo + "/" + resource,
        method="GET", headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "kral-owner-supervisor/1.0",
        })
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            payload = response.read(262145)
        if len(payload) > 262144:
            raise mission.MissionRejected("RESPONSE_TOO_LARGE")
        return json.loads(payload)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        raise mission.MissionRejected("GITHUB_READ_FAILED") from None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only verification of owner PR and CI job")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--run", type=int, required=True)
    a = ap.parse_args(argv)
    try:
        allowed = mission.validate_repository_inventory(
            mission.read_small_json(mission.REPO_INVENTORY, 16384))
        if a.repo not in allowed:
            raise mission.MissionRejected("REPO_NOT_ALLOWLISTED")
        token = os.environ.get("GITHUB_TOKEN", "")
        pr = github_get(a.repo, "pulls/" + str(a.pr), token)
        run = github_get(a.repo, "actions/runs/" + str(a.run), token)
        output = evaluate(a.repo, a.pr, a.run, pr, run, allowed)
        print(json.dumps(output, ensure_ascii=False))
        return 0 if output["status"] == "CI_PASS_AWAIT_OWNER_REVIEW" else 1
    except (mission.MissionRejected, TypeError, KeyError, OSError) as e:
        print("SUPERVISOR_BLOCKED: " +
              (str(e) if isinstance(e, mission.MissionRejected) else "BAD_INPUT"),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
