#!/usr/bin/env python3
"""Reject recognizable credentials in tracked sources and expanded APK entries.

Only file names and rule identifiers are reported. This is a bounded offline
pattern scan, not proof that arbitrary secrets cannot exist.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import zipfile

RULES = {
    "OPENAI_STYLE_KEY": rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}",
    "GOOGLE_API_KEY": rb"\bAIza[0-9A-Za-z_-]{35}",
    "GITHUB_TOKEN": rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})",
    "PRIVATE_KEY_PEM": rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
}


def rules_matched(data: bytes) -> list[str]:
    return [name for name, pattern in RULES.items() if re.search(pattern, data)]


def scan(apk: Path | None = None) -> list[str]:
    findings = []
    paths = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    for raw in filter(None, paths):
        path = Path(raw.decode())
        for rule in rules_matched(path.read_bytes()):
            findings.append(f"SOURCE:{path}:{rule}")
    if apk is not None:
        with zipfile.ZipFile(apk) as archive:
            total = sum(entry.file_size for entry in archive.infolist())
            if total > 256 * 1024 * 1024:
                raise ValueError("APK_SCAN_SIZE_LIMIT")
            for entry in archive.infolist():
                if not entry.is_dir():
                    for rule in rules_matched(archive.read(entry)):
                        findings.append(f"APK:{entry.filename}:{rule}")
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path)
    args = parser.parse_args()
    findings = scan(args.apk)
    for finding in findings:
        print(finding)
    if findings:
        raise SystemExit("DELIVERY_SECRET_PATTERN_DETECTED")
    print("DELIVERY_SECRET_PATTERN_SCAN_PASSED")


if __name__ == "__main__":
    main()
