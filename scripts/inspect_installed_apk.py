#!/usr/bin/env python3
"""Read-only identity inventory of an APK installed on an explicitly selected Android device.

Uses only adb shell pm path and adb pull to copy public installed APK files into
an automatically deleted local temporary directory. No install/uninstall, app
private data read, device settings, remote service, or keystore access.

The output is *not* evidence of successful upgrade, data migration, owner
identity, or Play Store approval. If any split APK cannot be verified, fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from scripts.check_android_upgrade import (
    UpgradeRejected,
    inspect_apk,
    require_file_unchanged,
    sha256_file,
    verify_expected_sha256,
    verify_upgrade,
)

PACKAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+")
SERIAL_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:\-]{0,127}")
HEX_RE = re.compile(r"[a-fA-F0-9]{64}")
MAX_APKS = 32


def parse_pm_paths(output: str) -> tuple[str, ...]:
    """Require one base.apk and a bounded, unambiguous Android pm path listing."""
    entries = output.splitlines()
    if not 1 <= len(entries) <= MAX_APKS:
        raise UpgradeRejected("INSTALLED_APK_PATHS_MISSING_OR_EXCESSIVE")
    paths: list[str] = []
    for line in entries:
        if not line.startswith("package:"):
            raise UpgradeRejected("INSTALLED_APK_PATH_INVALID")
        path = line[len("package:"):].strip()
        if (len(path) > 1024 or not path.startswith("/") or
                not path.endswith(".apk") or
                any(ch.isspace() or ord(ch) < 32 for ch in path) or
                "//" in path or ".." in PurePosixPath(path).parts):
            raise UpgradeRejected("INSTALLED_APK_PATH_INVALID")
        paths.append(path)
    if len(set(paths)) != len(paths) or sum(
            PurePosixPath(p).name == "base.apk" for p in paths) != 1:
        raise UpgradeRejected("INSTALLED_APK_BASE_MISSING_OR_AMBIGUOUS")
    return tuple(paths)


def run_adb(argv: list[str], *, timeout: int = 60) -> str:
    try:
        process = subprocess.run(
            argv, capture_output=True, text=True, check=True, timeout=timeout,
        )
        return process.stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise UpgradeRejected("ADB_READ_ONLY_COMMAND_FAILED") from exc


def checked_serial(value: str) -> str:
    if not SERIAL_RE.fullmatch(value):
        raise UpgradeRejected("ADB_DEVICE_SERIAL_INVALID")
    return value


def checked_package(value: str) -> str:
    if not PACKAGE_RE.fullmatch(value):
        raise UpgradeRejected("ADB_PACKAGE_ID_INVALID")
    return value


def probe(
    *, serial: str, package: str, adb: str = "adb", aapt: str = "aapt",
    apksigner: str = "apksigner", candidate: Path | None = None,
    expected_candidate_sha256: str | None = None,
    expected_owner_cert_sha256: str | None = None,
) -> dict[str, object]:
    """Inspect installed identity and optionally compare a pinned, nondebuggable APK.

    Intentionally does not infer possession of the device, backup validity,
    signer lineage, or data-safe upgrade from a matching APK identity.
    """
    serial = checked_serial(serial)
    package = checked_package(package)
    if (candidate is None) != (expected_candidate_sha256 is None):
        raise UpgradeRejected("CANDIDATE_AND_PIN_MUST_BE_SUPPLIED_TOGETHER")
    # A file hash alone is not the owner's signing identity. Reject an
    # otherwise plausible release candidate unless its signer is pinned.
    if candidate is not None and expected_owner_cert_sha256 is None:
        raise UpgradeRejected("OWNER_CERT_PIN_REQUIRED_FOR_CANDIDATE")
    if expected_owner_cert_sha256 is not None and not HEX_RE.fullmatch(expected_owner_cert_sha256):
        raise UpgradeRejected("EXPECTED_OWNER_CERT_INVALID")

    # Require the caller to explicitly identify the device. No adb device
    # auto-selection, no shell=True, and no APK installation path in this tool.
    paths = parse_pm_paths(run_adb([adb, "-s", serial, "shell", "pm", "path", package]))
    base_remote = next(p for p in paths if PurePosixPath(p).name == "base.apk")
    sorted_paths = (base_remote,) + tuple(p for p in paths if p != base_remote)

    with TemporaryDirectory(prefix="kral-installed-apks-") as temp_dir:
        local_paths: list[Path] = []
        for idx, remote_path in enumerate(sorted_paths):
            destination = Path(temp_dir) / f"package-{idx}.apk"
            run_adb([adb, "-s", serial, "pull", remote_path, str(destination)], timeout=120)
            if not destination.is_file() or destination.stat().st_size == 0:
                raise UpgradeRejected("ADB_PULLED_APK_MISSING_OR_EMPTY")
            local_paths.append(destination)

        # An install/update can replace the base/split paths while adb pull is
        # reading them. Refuse mixed-version snapshots instead of implying the
        # copied files still describe the currently installed package.
        confirmed_paths = parse_pm_paths(run_adb(
            [adb, "-s", serial, "shell", "pm", "path", package]
        ))
        if set(confirmed_paths) != set(paths):
            raise UpgradeRejected("INSTALLED_PACKAGE_CHANGED_DURING_PROBE")

        hashes = [sha256_file(path) for path in local_paths]
        identities = [inspect_apk(path, aapt=aapt, apksigner=apksigner) for path in local_paths]
        for idx, identity in enumerate(identities):
            require_file_unchanged(local_paths[idx], hashes[idx])
            if (identity.package != package or
                    identity.version_code != identities[0].version_code or
                    identity.signing_cert_sha256 != identities[0].signing_cert_sha256):
                raise UpgradeRejected("INSTALLED_SPLIT_IDENTITY_MISMATCH")

        installed = identities[0]
        if expected_owner_cert_sha256 is not None and not hmac.compare_digest(
                installed.signing_cert_sha256, expected_owner_cert_sha256.lower()):
            raise UpgradeRejected("INSTALLED_OWNER_CERT_MISMATCH")

        report: dict[str, object] = {
            "status": "INSTALLED_APK_IDENTITY_OBSERVED_NOT_UPGRADE_APPROVAL",
            "package": package,
            "installed_version_code": installed.version_code,
            "installed_signer_cert_sha256": installed.signing_cert_sha256,
            "installed_debuggable": installed.debuggable,
            "installed_split_apk_count": len(identities) - 1,
            "installed_base_apk_sha256": hashes[0],
            "expected_owner_cert_verified": expected_owner_cert_sha256 is not None,
            "apk_source_observed_on_selected_device": True,
            "device_owner_verified": False,
            "upgrade_performed": False,
            "upgrade_success_verified": False,
            "database_migration_verified": False,
            "play_accepted": False,
        }
        if candidate is not None and expected_candidate_sha256 is not None:
            digest = verify_expected_sha256(candidate, expected_candidate_sha256)
            candidate_identity = inspect_apk(candidate, aapt=aapt, apksigner=apksigner)
            require_file_unchanged(candidate, digest)
            verify_upgrade(installed, candidate_identity, require_release=True)
            if expected_owner_cert_sha256 is not None and not hmac.compare_digest(
                    candidate_identity.signing_cert_sha256,
                    expected_owner_cert_sha256.lower()):
                raise UpgradeRejected("CANDIDATE_OWNER_CERT_MISMATCH")
            report.update({
                "status": "APK_IDENTITIES_COMPATIBLE_NOT_INSTALLATION_PROOF",
                "candidate_version_code": candidate_identity.version_code,
                "candidate_sha256": digest,
                "candidate_nondebuggable": True,
            })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Exact authorized adb device serial (no auto-selection)")
    parser.add_argument("--package", default="com.example.gptasistan.genesis")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--aapt", default="aapt")
    parser.add_argument("--apksigner", default="apksigner")
    parser.add_argument("--candidate-apk", type=Path)
    parser.add_argument("--expected-candidate-sha256")
    parser.add_argument("--expected-owner-cert-sha256")
    args = parser.parse_args()
    try:
        result = probe(
            serial=args.serial, package=args.package, adb=args.adb,
            aapt=args.aapt, apksigner=args.apksigner,
            candidate=args.candidate_apk,
            expected_candidate_sha256=args.expected_candidate_sha256,
            expected_owner_cert_sha256=args.expected_owner_cert_sha256,
        )
    except (UpgradeRejected, OSError) as exc:
        reason = str(exc) if isinstance(exc, UpgradeRejected) else "LOCAL_FILE_READ_FAILED"
        print(json.dumps({"status": "BLOCKED", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
