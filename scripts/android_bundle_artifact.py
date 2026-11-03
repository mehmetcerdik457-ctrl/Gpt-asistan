#!/usr/bin/env python3
"""Record an unsigned Android App Bundle with fail-closed source provenance.

This artifact is for review/build verification only. It is NOT signed, Play-ready,
or proof of device, model-provider, or Play Console acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
OUTPUT_NAME = "app-release-unsigned.aab"


def record_unsigned_bundle(bundle: Path, output: Path, source_sha: str, expected_sha: str) -> dict:
    if not SOURCE_SHA.fullmatch(expected_sha) or source_sha != expected_sha:
        raise ValueError("SOURCE_SHA_MISMATCH")
    if not bundle.is_file() or bundle.suffix != ".aab":
        raise ValueError("AAB_FILE_INVALID")

    try:
        with zipfile.ZipFile(bundle) as archive:
            names = set(archive.namelist())
            if archive.testzip() is not None:
                raise ValueError("AAB_ZIP_CORRUPT")
            if "base/manifest/AndroidManifest.xml" not in names:
                raise ValueError("AAB_MANIFEST_MISSING")
            # An unsigned candidate must not unexpectedly contain JAR signing material.
            if any(name.startswith("META-INF/") and name.upper().endswith((".RSA", ".DSA", ".EC")) for name in names):
                raise ValueError("AAB_UNEXPECTED_SIGNATURE")
    except zipfile.BadZipFile as exc:
        raise ValueError("AAB_ZIP_INVALID") from exc

    output.mkdir(parents=True, exist_ok=True)
    destination = output / OUTPUT_NAME
    if bundle.resolve() != destination.resolve():
        shutil.copyfile(bundle, destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    metadata = {
        "artifact": OUTPUT_NAME,
        "sha256": digest,
        "size_bytes": destination.stat().st_size,
        "source_commit": source_sha,
        "expected_source_commit": expected_sha,
        "exact_source_head_verified": True,
        "signing_status": "UNSIGNED",
        "play_upload_ready": False,
        "play_console_validated": False,
        "physical_device_tested": False,
        "live_model_tested": False,
    }
    (output / "aab-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "AAB-SHA256SUMS").write_text(f"{digest}  {OUTPUT_NAME}\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    actual_sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    metadata = record_unsigned_bundle(args.bundle, args.output, actual_sha, args.expected_sha)
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
