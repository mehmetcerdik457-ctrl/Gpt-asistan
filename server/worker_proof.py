"""Bounded read-only GitHub runner proof for eight specialist roles.

A role job proves a *separate GitHub Actions process*, not a Copilot agent,
local model, owner-approved code change, or completed customer task.
All commands and remote URLs are fixed in code. Never execute task text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

from server import mission_control

ROOT = Path(__file__).resolve().parents[1]
ROLE_TESTS = {
    "github-master-ai": ("server/tests", "test_kral_mission_dispatch.py"),
    "chief-engineer": ("server/tests", "test_kral_mission_control.py"),
    "android-engineer": ("server/tests", "test_genesis_agent_security.py"),
    "ai-ml-engineer": ("server/tests", "test_local_open_workers.py"),
    "mcp-engineer": ("kral/mcp", "test_youtube_server.py"),
    "ci-cd-engineer": ("server/tests", "test_legacy_recovered_agents.py"),
    "test-engineer": ("server/tests", "test_kral_mission_control.py"),
    "security-auditor": ("server/tests", "test_genesis_agent_security.py"),
}
GITHUB_REPO_URL = "https://api.github.com/repos/mehmetcerdik457-ctrl/Gpt-asistan"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_public_repo() -> str:
    """A real fixed-destination internet read; no private tokens are used."""
    req = urllib.request.Request(
        GITHUB_REPO_URL, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "kral-readonly-runner/1",
        })
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=12) as response:
            raw = response.read(131073)
        if len(raw) > 131072:
            return "BLOCKED_OVERSIZED_RESPONSE"
        result = json.loads(raw)
        if result.get("full_name") != "mehmetcerdik457-ctrl/Gpt-asistan":
            return "BLOCKED_WRONG_REPOSITORY"
        return "LIVE_PUBLIC_GITHUB_READ"
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError, TypeError):
        return "BLOCKED_NETWORK_OR_GITHUB"


def execute_role(role: str, *, network_probe=probe_public_repo) -> dict:
    if role not in ROLE_TESTS:
        raise ValueError("ROLE_NOT_ALLOWLISTED")
    profile = ROOT / ".github" / "agents" / (role + ".agent.md")
    if not profile.is_file() or profile.is_symlink():
        raise RuntimeError("AGENT_PROFILE_UNAVAILABLE")
    content = profile.read_bytes()
    if len(content) > 65536 or not content.startswith(b"---\n"):
        raise RuntimeError("AGENT_PROFILE_INVALID")
    test_dir, test_pattern = ROLE_TESTS[role]
    command = [
        sys.executable, "-m", "unittest", "discover",
        "-s", test_dir, "-p", test_pattern, "-q",
    ]
    # Never forward GitHub secrets, proxy credentials or user-supplied shell text.
    clean_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT),
        "LANG": "C.UTF-8",
    }
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=clean_env, capture_output=True, text=True,
            timeout=160, check=False,
        )
        passed = result.returncode == 0
        combined = (result.stdout + result.stderr)[:131072]
        evidence_hash = hashlib.sha256(combined.encode("utf-8", errors="replace")).hexdigest()
        test_state = "PASS" if passed else "BLOCKED_TEST_FAILURE"
    except (OSError, subprocess.TimeoutExpired):
        evidence_hash = None
        test_state = "BLOCKED_TEST_RUNNER"
    try:
        network_state = network_probe()
    except Exception:
        network_state = "BLOCKED_NETWORK_PROBE"
    status = ("REAL_PROCESS_PROBE_PASS_NO_MODEL" if
              test_state == "PASS" and network_state == "LIVE_PUBLIC_GITHUB_READ"
              else "BLOCKED_OR_PARTIAL_NO_MODEL")
    return {
        "schema": 1, "role": role, "mode": status,
        "profile_sha256": hashlib.sha256(content).hexdigest(),
        "test_file": test_dir + "/" + test_pattern,
        "test_result": test_state, "test_output_sha256": evidence_hash,
        "github_read": network_state,
        "github_actions_run_id": os.environ.get("GITHUB_RUN_ID", "NOT_IN_ACTIONS"),
        "source_sha": os.environ.get("GITHUB_SHA", "NOT_IN_ACTIONS"),
        "logical_worker_slot_capacity": mission_control.MAX_WORKERS,
        "real_ai_model_calls": 0,
        "code_changes": 0, "youtube_oauth": "NOT_TESTED",
        "owner_acceptance": "NOT_GRANTED",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only role-specific subprocess and GitHub API checks")
    parser.add_argument("--role", required=True, choices=sorted(ROLE_TESTS))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    output = execute_role(args.role)
    encoded = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.out.is_symlink() or not args.out.parent.is_dir():
        print("EVIDENCE_PATH_DENIED", file=sys.stderr)
        return 2
    args.out.write_text(encoded, encoding="utf-8")
    print(json.dumps({"role": args.role, "mode": output["mode"],
                      "evidence_file": str(args.out)}, ensure_ascii=False))
    return 0 if output["mode"] == "REAL_PROCESS_PROBE_PASS_NO_MODEL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
