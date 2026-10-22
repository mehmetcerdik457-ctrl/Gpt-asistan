#!/usr/bin/env python3
"""Verify a built APK and write reproducible delivery metadata, without secrets."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile


def command(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def field(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"Required APK metadata missing: {pattern}")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sdk", type=Path, default=os.environ.get("ANDROID_HOME"))
    parser.add_argument("--build-tools", default="34.0.0")
    args = parser.parse_args()
    if not args.sdk:
        parser.error("--sdk or ANDROID_HOME is required")
    sdk_tools = args.sdk / "build-tools" / args.build_tools
    badging = command(str(sdk_tools / "aapt"), "dump", "badging", str(args.apk))
    signature = command(str(sdk_tools / "apksigner"), "verify", "--verbose", "--print-certs", str(args.apk))
    package = field(r"^package: name='([^']+)'", badging)
    if "split=" in badging.splitlines()[0]:
        raise ValueError("A split APK is not a standalone deliverable")
    apk_hash = hashlib.sha256(args.apk.read_bytes()).hexdigest()
    with zipfile.ZipFile(args.apk) as archive:
        native_abis = sorted({name.split("/")[1] for name in archive.namelist() if name.startswith("lib/") and name.endswith(".so")})
        if archive.testzip() is not None:
            raise ValueError("APK ZIP integrity check failed")
    metadata = {
        "source_commit": command("git", "rev-parse", "HEAD").strip(),
        "source_branch": command("git", "branch", "--show-current").strip(),
        "source_tree_clean": not command("git", "status", "--porcelain").strip(),
        "apk": args.apk.name,
        "sha256": apk_hash,
        "size_bytes": args.apk.stat().st_size,
        "package": package,
        "version_code": int(field(r"^package: .*versionCode='([^']+)'", badging)),
        "version_name": field(r"^package: .*versionName='([^']+)'", badging),
        "min_sdk": int(field(r"^sdkVersion:'([^']+)'", badging)),
        "target_sdk": int(field(r"^targetSdkVersion:'([^']+)'", badging)),
        "permissions": re.findall(r"^uses-permission: name='([^']+)'", badging, re.MULTILINE),
        "native_abis": native_abis,
        "architecture_note": "Contains no native libraries; Android bytecode is architecture independent" if not native_abis else "Native libraries restrict supported architectures",
        "signer_certificate_sha256": re.findall(r"^Signer #\d+ certificate SHA-256 digest: (\S+)", signature, re.MULTILINE),
        "signature_verified": True,
        "debuggable": "application-debuggable" in badging,
        "standalone_apk": True,
        "physical_device_tested": False,
        "emulator_tested": False,
        "live_model_tested": False,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
    }
    if not metadata["signer_certificate_sha256"]:
        raise ValueError("No signing certificate SHA-256 returned by apksigner")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "apk-metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    (args.output / "apk-badging.txt").write_text(badging)
    (args.output / "apk-signature.txt").write_text(signature)
    (args.output / "APK-SHA256SUMS").write_text(f"{apk_hash}  {args.apk.name}\n")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
