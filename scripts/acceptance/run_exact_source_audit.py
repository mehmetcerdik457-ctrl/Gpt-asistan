"""Independently test an exact Git commit with real local gateway processes.

Remote model behavior, credentials, prompts and stored data are synthetic. This
runner never accesses a live model or modifies the checked-out repository source.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit", help="Exact full source commit SHA to archive and test")
    parser.add_argument(
        "--output", type=Path,
        default=REPO_ROOT / "build" / "acceptance" / "independent-results.json",
        help="JSON evidence destination (default: build/acceptance/independent-results.json)",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        parser.error("An exact full commit SHA is required")
    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-e", args.commit + "^{commit}"],
        check=True,
    )
    archive = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", args.commit],
        capture_output=True, check=True,
    ).stdout
    checks = []
    with tempfile.TemporaryDirectory(prefix="kral-exact-source-") as folder:
        source = Path(folder) / "source"
        source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            package.extractall(source, filter="data")
        # Test definitions and the fixture also come from the requested commit.
        harness = source / "scripts" / "acceptance"
        env = os.environ.copy()
        env["KRAL_INDEPENDENT_SOURCE"] = str(source)
        env["PYTHONPATH"] = str(source)
        commands = [
            ("real-local-runtime", 6, [
                sys.executable, "-m", "unittest", "discover", "-s", str(harness),
                "-p", "test_independent_acceptance.py", "-v",
            ]),
            ("synthetic-secret-reflection", 4, [
                sys.executable, str(harness / "check_current_secret_reflection.py"),
            ]),
        ]
        for label, expected_count, command in commands:
            try:
                result = subprocess.run(
                    command, cwd=source, env=env,
                    capture_output=True, text=True, timeout=60,
                )
                stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout or b""
                stderr = exc.stderr or b""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode(errors="replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode(errors="replace")
                stderr += "\nIndependent acceptance subprocess exceeded 60 seconds.\n"
                exit_code = 124
            count = re.search(r"Ran (\d+) tests?", stderr)
            actual_count = int(count.group(1)) if count else None
            checks.append({
                "name": label, "exit_code": exit_code,
                "tests": actual_count, "expected_tests": expected_count,
                "passed": exit_code == 0 and actual_count == expected_count,
                "output": stdout + stderr,
            })
        gateway_sha = hashlib.sha256((source / "server" / "gateway.py").read_bytes()).hexdigest()
    report = {
        "source_commit": args.commit,
        "source_git_archive_sha256": hashlib.sha256(archive).hexdigest(),
        "gateway_file_sha256": gateway_sha,
        "scope": (
            "Real loopback HTTP, service process restarts, P-256 and SQLite; "
            "synthetic upstream provider, keys and data. "
            "No paid service, physical device or production enrollment is claimed."
        ),
        "passed": all(row["passed"] for row in checks),
        "tests": sum(row["tests"] or 0 for row in checks),
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "report": str(args.output), "source_commit": args.commit,
        "passed": report["passed"], "tests": report["tests"],
        "gateway_sha256": gateway_sha,
    }, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
