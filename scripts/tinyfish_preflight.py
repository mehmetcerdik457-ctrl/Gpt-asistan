#!/usr/bin/env python3
"""Offline TinyFish CLI preflight. Never prints credentials or makes network calls."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Callable, Mapping


def _version(command: str, which: Callable[[str], str | None]) -> str | None:
    executable = which(command)
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = (result.stdout or result.stderr).strip()
    return value[:80] if result.returncode == 0 and value else None


def _major(version: str | None) -> int | None:
    if not version:
        return None
    match = re.search(r"(?:^|v)(\d+)(?:\.|$)", version)
    return int(match.group(1)) if match else None


def inspect_environment(
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> dict:
    env = os.environ if environ is None else environ
    node_version = _version("node", which)
    npm_version = _version("npm", which)
    tinyfish_path = which("tinyfish")
    node_major = _major(node_version)

    return {
        "mode": "OFFLINE_PREFLIGHT",
        "node_version": node_version or "NOT_FOUND",
        "node_major": node_major,
        "node_24_or_newer": node_major is not None and node_major >= 24,
        "npm_detected": npm_version is not None,
        "tinyfish_cli_detected": tinyfish_path is not None,
        "tinyfish_api_key_present": bool(env.get("TINYFISH_API_KEY", "").strip()),
        "api_key_value_exposed": False,
        "network_requests_made": 0,
        "browser_runs_started": 0,
        "paid_operations_started": 0,
    }


if __name__ == "__main__":
    print(json.dumps(inspect_environment(), ensure_ascii=False, indent=2, sort_keys=True))
