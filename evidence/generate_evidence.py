#!/usr/bin/env python3
"""Produce evidence bundle (run log + reports) in evidence/out/ for upload to Drive."""
import datetime
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "evidence", "out")


def run(cmd):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return "$ %s\n(exit %d)\n%s%s\n" % (" ".join(cmd), p.returncode, p.stdout, p.stderr)


def main():
    os.makedirs(OUT, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    log = "Evidence run at %s\n\n" % stamp
    log += run(["bash", "scripts/validate_structure.sh"])
    log += run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    log += run(["git", "log", "--oneline", "-n", "10"])
    with open(os.path.join(OUT, "run.log"), "w", encoding="utf-8") as fh:
        fh.write(log)
    for name in ("INVENTORY.md", "MIGRATION_REPORT.md", "API_DISCOVERY.md", "SECURITY_FINDINGS.md", "KNOWN_ISSUES.md"):
        src = os.path.join(ROOT, "docs", name)
        if os.path.exists(src):
            shutil.copy(src, OUT)
    print("evidence written to", OUT)


if __name__ == "__main__":
    main()
