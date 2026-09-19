#!/usr/bin/env python3
"""Fail closed on GitHub platform configuration regressions."""
from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENT_DIR = ROOT / ".github" / "agents"
WORKFLOW_DIR = ROOT / ".github" / "workflows"

EXPECTED_AGENTS = {
    "android-engineer.agent.md",
    "apk-forensic.agent.md",
    "chief-engineer.agent.md",
    "ci-cd-engineer.agent.md",
    "code-reviewer.agent.md",
    "release-engineer.agent.md",
    "security-auditor.agent.md",
    "test-engineer.agent.md",
}

MCP_ALLOW = {
    "security-auditor.agent.md": {
        "github/get_file_contents",
        "github/search_code",
        "github/pull_request_read",
    },
    "apk-forensic.agent.md": {
        "github/get_file_contents",
        "github/search_code",
    },
    "code-reviewer.agent.md": {
        "github/get_file_contents",
        "github/search_code",
        "github/pull_request_read",
    },
}

READ_ONLY_AGENTS = {
    "security-auditor.agent.md",
    "apk-forensic.agent.md",
    "code-reviewer.agent.md",
    "release-engineer.agent.md",
}

CRITICAL_CONCURRENCY_WORKFLOWS = {
    "advanced-forensics-toolchain.yml",
    "android.yml",
    "cancel-stale-runs.yml",
    "ci.yml",
    "dependency-submission.yml",
    "direct-head-matrix.yml",
    "gate0-forensics.yml",
    "platform-security-state.yml",
    "reproducibility.yml",
    "security-supply-chain.yml",
}

ACTION_REF = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-fA-F]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")


def fail(message: str) -> None:
    print(f"PLATFORM_POLICY_FAIL={message}", file=sys.stderr)
    raise SystemExit(1)


def frontmatter(path: pathlib.Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        fail(f"{path.name}: missing YAML frontmatter opener")
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(f"{path.name}: missing YAML frontmatter closer")
    data: dict[str, str] = {}
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            fail(f"{path.name}: malformed frontmatter line: {raw}")
        key, value = raw.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def parse_tools(path: pathlib.Path, raw: str) -> list[str]:
    try:
        value = ast.literal_eval(raw)
    except (SyntaxError, ValueError) as exc:
        fail(f"{path.name}: tools must be an explicit quoted list: {exc}")
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        fail(f"{path.name}: tools must be list[str]")
    return value


def validate_agents() -> None:
    actual = {p.name for p in AGENT_DIR.glob("*.agent.md")}
    if actual != EXPECTED_AGENTS:
        fail(f"agent set mismatch expected={sorted(EXPECTED_AGENTS)} actual={sorted(actual)}")
    for path in sorted(AGENT_DIR.glob("*.agent.md")):
        fm = frontmatter(path)
        if not fm.get("description"):
            fail(f"{path.name}: description is required")
        if "tools" not in fm:
            fail(f"{path.name}: explicit tools list required; omission enables all tools")
        tools = parse_tools(path, fm["tools"])
        if "*" in tools or any(t.endswith("/*") for t in tools):
            fail(f"{path.name}: wildcard tools are forbidden")
        if path.name in READ_ONLY_AGENTS and "edit" in tools:
            fail(f"{path.name}: read-only role cannot use edit")
        if path.name in {"security-auditor.agent.md", "code-reviewer.agent.md"} and "execute" in tools:
            fail(f"{path.name}: reviewer role cannot use execute")
        github_tools = {t for t in tools if t.startswith("github/")}
        allowed = MCP_ALLOW.get(path.name, set())
        if github_tools - allowed:
            fail(f"{path.name}: unauthorized GitHub MCP tools {sorted(github_tools - allowed)}")


def validate_workflows() -> None:
    workflows = sorted(WORKFLOW_DIR.glob("*.yml"))
    if not workflows:
        fail("no workflows found")
    count = 0
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^permissions:\s*$", text) is None:
            fail(f"{path.name}: explicit permissions block required")
        if re.search(r"(?m)^\s*permissions:\s*write-all\s*$", text):
            fail(f"{path.name}: write-all is forbidden")
        if re.search(r"(?m)^\s*python-version:\s*[\'\"]?3\.x[\'\"]?\s*$", text):
            fail(f"{path.name}: floating Python versions are forbidden; pin an explicit minor version")
        if re.search(r"(?m)^\s*pull_request_target\s*:", text):
            fail(f"{path.name}: pull_request_target is forbidden")
        if path.name in CRITICAL_CONCURRENCY_WORKFLOWS:
            if re.search(r"(?m)^concurrency:\s*$", text) is None:
                fail(f"{path.name}: top-level concurrency block required")
            if "cancel-in-progress: true" not in text:
                fail(f"{path.name}: concurrency must cancel stale runs")
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if "uses: actions/checkout@" in line:
                window = "\n".join(lines[index:index + 10])
                if re.search(r"(?m)^\s*persist-credentials:\s*false\s*$", window) is None:
                    fail(f"{path.name}: actions/checkout must set persist-credentials: false")
        for line in lines:
            match = USES.match(line)
            if not match:
                continue
            count += 1
            ref = match.group(1)
            if ref.startswith("./"):
                continue
            if not ACTION_REF.fullmatch(ref):
                fail(f"{path.name}: action must be pinned to immutable SHA: {ref}")
    if count == 0:
        fail("no action references found")
    print(f"IMMUTABLE_ACTION_REFS={count}")



def validate_governance() -> None:
    required = [
        ROOT / ".github" / "CODEOWNERS",
        ROOT / ".github" / "SECURITY.md",
        ROOT / ".github" / "dependabot.yml",
        ROOT / ".github" / "pull_request_template.md",
    ]
    for path in required:
        if not path.is_file():
            fail(f"missing governance file: {path.relative_to(ROOT)}")

    duplicate = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
    if duplicate.exists():
        fail("duplicate PR template forbidden; keep .github/pull_request_template.md only")

    smoke = (WORKFLOW_DIR / "apk-forensic-smoke.yml").read_text(encoding="utf-8")
    if "source_run_id:" not in smoke or "inputs.source_run_id" not in smoke:
        fail("apk-forensic-smoke.yml must use an explicit workflow_dispatch source_run_id")
    if re.search(r"(?m)^\s*run-id:\s*[0-9]+\s*$", smoke):
        fail("apk-forensic-smoke.yml cannot pin a stale literal workflow run id")

    backup = (WORKFLOW_DIR / "repository-backup-drill.yml").read_text(encoding="utf-8")
    if re.search(r"(?m)^\s*-\s*main\s*$", backup) is None:
        fail("repository-backup-drill.yml must run on main")
    if "copilot-agent-upgrade-20260917" in backup:
        fail("repository-backup-drill.yml cannot depend on a temporary feature branch")

    stale = (WORKFLOW_DIR / "cancel-stale-runs.yml").read_text(encoding="utf-8")
    if "branches-ignore: [main]" not in stale:
        fail("cancel-stale-runs.yml must target non-main branches via branches-ignore: [main]")

    print("GOVERNANCE_POLICY=PASS")


def main() -> None:
    validate_agents()
    validate_workflows()
    validate_governance()
    print("AGENT_POLICY=PASS")
    print("WORKFLOW_SUPPLY_CHAIN_POLICY=PASS")
    print("PLATFORM_POLICY=PASS")


if __name__ == "__main__":
    main()
