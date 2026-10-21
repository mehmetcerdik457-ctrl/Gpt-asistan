"""One-time branch-push proof: fixed CI tests -> owner issue #40 comment.

Unlike the default-branch issue-event workflow, this pilot runs only after
a commit to an isolated integration branch. It never calls AI services,
changes code, or executes commands from issue text.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from server import github_issue_bridge as bridge

PILOT_ISSUE = 40
PILOT_BRANCH = "refs/heads/integration/cihat-github-task-bridge-20261021"
ISSUE_API = f"https://api.github.com/repos/{bridge.REPOSITORY}/issues/{PILOT_ISSUE}"


def approved_environment(env):
    return (
        env.get("GITHUB_REPOSITORY") == bridge.REPOSITORY
        and env.get("GITHUB_ACTOR") == bridge.OWNER_LOGIN
        and env.get("GITHUB_REF") == PILOT_BRANCH
        and env.get("GITHUB_EVENT_NAME") == "push"
        and re.fullmatch(r"[a-f0-9]{40}", env.get("GITHUB_SHA", "")) is not None
        and re.fullmatch(r"[0-9]{1,20}", env.get("GITHUB_RUN_ID", "")) is not None
    )


def read_current_issue(token):
    if not token or "\n" in token or "\r" in token:
        raise bridge.TaskRejected("PILOT_GITHUB_TOKEN_DENIED")
    req = urllib.request.Request(ISSUE_API, method="GET", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kral-fixed-pilot/1.0",
    })
    try:
        with urllib.request.build_opener(bridge.NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise bridge.TaskRejected("PILOT_ISSUE_OVERSIZED")
        issue = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        raise bridge.TaskRejected("PILOT_ISSUE_FETCH_FAILED") from None
    if not isinstance(issue, dict) or issue.get("number") != PILOT_ISSUE:
        raise bridge.TaskRejected("PILOT_ISSUE_INVALID")
    return issue


def run():
    if not approved_environment(os.environ):
        raise bridge.TaskRejected("PILOT_ENV_DENIED")
    token = os.environ.get("GITHUB_TOKEN", "")
    issue = read_current_issue(token)
    # Reuse precisely the same policy as normal owner-created fixed CI issues.
    event = {
        "action": "opened",
        "repository": {"full_name": bridge.REPOSITORY},
        "issue": issue,
    }
    number, _ = bridge.validate_check_event(event)
    if number != PILOT_ISSUE:
        raise bridge.TaskRejected("PILOT_NUMBER_DENIED")
    if bridge.already_answered(number, token, bridge.CHECK_MARKER):
        print("PILOT_ALREADY_POSTED")
        return
    comment = bridge.make_check_comment(
        Path("kral-checks.log"),
        os.environ["GITHUB_RUN_ID"],
        os.environ["GITHUB_SHA"],
    )
    bridge.github_json("POST", f"/issues/{PILOT_ISSUE}/comments", token, {"body": comment})
    print("PILOT_CI_EVIDENCE_POSTED")


if __name__ == "__main__":
    try:
        run()
    except (bridge.TaskRejected, OSError, KeyError, TypeError):
        print("PILOT_BLOCKED", file=sys.stderr)
        sys.exit(1)
