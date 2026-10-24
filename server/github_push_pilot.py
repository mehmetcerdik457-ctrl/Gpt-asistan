"""Owner-gated reusable GitHub branch task intake, fixed CI only.

A task ticket selects a GitHub issue; its body NEVER becomes a command,
model prompt, URL or write operation. Neither device nor source code is modified
by tasks. Only the branch integration push triggers this script.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from server import github_issue_bridge as bridge

PILOT_BRANCH = "refs/heads/integration/genesis8-copilot-20261024"
TASK_TITLE_PREFIX = "[GENESIS8]"
TICKET_PATH = Path(__file__).with_name("task_ticket.json")
TICKET_LIMIT = 2048
ISSUE_LIMIT = 65536


def approved_environment(env):
    return (
        env.get("GITHUB_REPOSITORY") == bridge.REPOSITORY
        and env.get("GITHUB_ACTOR") == bridge.OWNER_LOGIN
        and env.get("GITHUB_REF") == PILOT_BRANCH
        and env.get("GITHUB_EVENT_NAME") == "push"
        and re.fullmatch(r"[a-f0-9]{40}", env.get("GITHUB_SHA", "")) is not None
        and re.fullmatch(r"[0-9]{1,20}", env.get("GITHUB_RUN_ID", "")) is not None
    )


def parse_ticket(ticket):
    if not isinstance(ticket, dict) or set(ticket) != {
        "schema", "repository", "operation", "issue_number"
    }:
        raise bridge.TaskRejected("TICKET_FORMAT_DENIED")
    if type(ticket["schema"]) is not int or ticket["schema"] != 1:
        raise bridge.TaskRejected("TICKET_SCHEMA_DENIED")
    if ticket["repository"] != bridge.REPOSITORY or ticket["operation"] != "fixed_ci":
        raise bridge.TaskRejected("TICKET_OPERATION_DENIED")
    number = ticket["issue_number"]
    if type(number) is not int or not 1 <= number <= 100000000:
        raise bridge.TaskRejected("TICKET_ISSUE_DENIED")
    return number


def load_ticket(path=TICKET_PATH):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > TICKET_LIMIT:
        raise bridge.TaskRejected("TICKET_FILE_DENIED")
    try:
        return parse_ticket(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, UnicodeError, OSError):
        raise bridge.TaskRejected("TICKET_CONTENT_DENIED") from None


def read_current_issue(token, issue_number):
    if (not isinstance(token, str) or not token or "\n" in token or "\r" in token
        or type(issue_number) is not int or not 1 <= issue_number <= 100000000):
        raise bridge.TaskRejected("ISSUE_READ_DENIED")
    url = f"https://api.github.com/repos/{bridge.REPOSITORY}/issues/{issue_number}"
    req = urllib.request.Request(url, method="GET", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kral-branch-task-queue/1.0",
    })
    try:
        with urllib.request.build_opener(bridge.NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(ISSUE_LIMIT + 1)
        if len(raw) > ISSUE_LIMIT:
            raise bridge.TaskRejected("ISSUE_RESPONSE_OVERSIZED")
        issue = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, TypeError):
        raise bridge.TaskRejected("ISSUE_FETCH_FAILED") from None
    if not isinstance(issue, dict) or type(issue.get("number")) is not int or issue["number"] != issue_number:
        raise bridge.TaskRejected("ISSUE_RESPONSE_INVALID")
    return issue


def run():
    if not approved_environment(os.environ):
        raise bridge.TaskRejected("TASK_ENV_DENIED")
    ticket_number = load_ticket()
    token = os.environ.get("GITHUB_TOKEN", "")
    issue = read_current_issue(token, ticket_number)
    event = {"action": "opened", "repository": {"full_name": bridge.REPOSITORY}, "issue": issue}
    checked_number, _ = bridge.validate_check_event(event, title_prefix=TASK_TITLE_PREFIX)
    if checked_number != ticket_number:
        raise bridge.TaskRejected("TASK_ISSUE_MISMATCH")
    if bridge.already_answered(ticket_number, token, bridge.CHECK_MARKER):
        print("TASK_ALREADY_REPLIED")
        return
    comment = bridge.make_check_comment(
        Path("kral-checks.log"),
        os.environ["GITHUB_RUN_ID"],
        os.environ["GITHUB_SHA"],
    )
    bridge.github_json("POST", f"/issues/{ticket_number}/comments", token, {"body": comment})
    print(f"TASK_FIXED_CI_POSTED_ISSUE_{ticket_number}")


if __name__ == "__main__":
    try:
        run()
    except (bridge.TaskRejected, OSError, KeyError, TypeError):
        print("TASK_BRIDGE_BLOCKED", file=sys.stderr)
        sys.exit(1)
