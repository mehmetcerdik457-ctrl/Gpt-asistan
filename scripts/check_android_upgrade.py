#!/usr/bin/env python3
"""Conservative offline APK-to-APK upgrade identity gate.

Reads local APK files through Android SDK aapt and apksigner; it does NOT touch
the device, install APKs, create a signing key or call an external service.
A compatible result is not evidence of successful installation or Play acceptance.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
import subprocess
import sys


class UpgradeRejected(ValueError):
    """Stop an unsafe or unverified APK upgrade."""


@dataclass(frozen=True)
class ApkIdentity:
    package: str
    version_code: int
    signing_cert_sha256: str
    debuggable: bool


PACKAGE_RE = re.compile(
    r"(?m)^package:\s+name='([A-Za-z][A-Za-z0-9_.]+)'\s+versionCode='([0-9]+)'(?:\s|$)"
)
SIGNER_RE = re.compile(
    r"(?m)^Signer #([1-9][0-9]*) certificate SHA-256 digest:\s*([0-9a-fA-F:]+)\s*$"
)


def parse_badging(output: str) -> tuple[str, int, bool]:
    matches = PACKAGE_RE.findall(output)
    if len(matches) != 1:
        raise UpgradeRejected("PACKAGE_METADATA_MISSING_OR_AMBIGUOUS")
    package, version_text = matches[0]
    version = int(version_text)
    if version < 1:
        raise UpgradeRejected("APK_VERSION_CODE_INVALID")
    debuggable = bool(re.search(r"(?m)^application-debuggable(?:\s|$)", output))
    return package, version, debuggable


def parse_signing_certificates(output: str) -> str:
    found = SIGNER_RE.findall(output)
    # Reject multiple signers/ambiguous signing identities rather than guessing.
    if len(found) != 1 or found[0][0] != "1":
        raise UpgradeRejected("APK_SIGNER_MISSING_OR_AMBIGUOUS")
    digest = found[0][1].replace(":", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise UpgradeRejected("APK_SIGNER_CERT_SHA256_INVALID")
    return digest


def _tool_output(argv: list[str]) -> str:
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, check=True, timeout=45
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise UpgradeRejected("ANDROID_SDK_TOOL_FAILED_OR_UNAVAILABLE") from exc
    return completed.stdout


def inspect_apk(path: Path, *, aapt: str, apksigner: str) -> ApkIdentity:
    if not path.is_file() or path.suffix.lower() != ".apk":
        raise UpgradeRejected("APK_INPUT_NOT_FOUND_OR_INVALID")
    package, version, debuggable = parse_badging(
        _tool_output([aapt, "dump", "badging", str(path)])
    )
    cert = parse_signing_certificates(
        _tool_output([apksigner, "verify", "--print-certs", str(path)])
    )
    return ApkIdentity(package, version, cert, debuggable)


def verify_upgrade(
    previous: ApkIdentity, candidate: ApkIdentity, *, require_release: bool = False
) -> None:
    if previous.package != candidate.package:
        raise UpgradeRejected("APK_PACKAGE_ID_CHANGED")
    if previous.signing_cert_sha256 != candidate.signing_cert_sha256:
        raise UpgradeRejected("APK_SIGNER_CERT_CHANGED")
    if candidate.version_code <= previous.version_code:
        raise UpgradeRejected("APK_VERSION_CODE_NOT_INCREASED")
    if require_release and candidate.debuggable:
        raise UpgradeRejected("CANDIDATE_IS_DEBUGGABLE")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_expected_sha256(path: Path, expected: str) -> str:
    """Require a SHA-256 pinned by independently recorded build evidence."""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise UpgradeRejected("APK_EXPECTED_SHA256_INVALID")
    try:
        observed = sha256_file(path)
    except OSError as exc:
        raise UpgradeRejected("APK_HASH_READ_FAILED") from exc
    if not hmac.compare_digest(observed, expected.lower()):
        raise UpgradeRejected("APK_SHA256_MISMATCH")
    return observed


def require_file_unchanged(path: Path, original_sha256: str) -> None:
    try:
        observed = sha256_file(path)
    except OSError as exc:
        raise UpgradeRejected("APK_HASH_READ_FAILED") from exc
    if not hmac.compare_digest(original_sha256, observed):
        raise UpgradeRejected("APK_CHANGED_DURING_INSPECTION")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-apk", type=Path, required=True)
    parser.add_argument("--candidate-apk", type=Path, required=True)
    parser.add_argument("--aapt", default="aapt", help="Path to Android SDK aapt")
    parser.add_argument("--apksigner", default="apksigner", help="Path to SDK apksigner")
    parser.add_argument(
        "--expected-candidate-sha256", required=True,
        help="Exact SHA-256 recorded by independently trusted candidate build evidence",
    )
    parser.add_argument(
        "--expected-previous-sha256",
        help="Optional expected SHA-256 of verified currently installed APK copy",
    )
    parser.add_argument(
        "--require-release", action="store_true",
        help="Reject a debuggable candidate; does not establish Play readiness",
    )
    args = parser.parse_args()
    try:
        candidate_digest = verify_expected_sha256(
            args.candidate_apk, args.expected_candidate_sha256
        )
        if args.expected_previous_sha256:
            previous_digest = verify_expected_sha256(
                args.previous_apk, args.expected_previous_sha256
            )
        else:
            previous_digest = sha256_file(args.previous_apk)
        old = inspect_apk(args.previous_apk, aapt=args.aapt, apksigner=args.apksigner)
        new = inspect_apk(args.candidate_apk, aapt=args.aapt, apksigner=args.apksigner)
        # Reject files that changed while external Android SDK tools inspected them.
        require_file_unchanged(args.previous_apk, previous_digest)
        require_file_unchanged(args.candidate_apk, candidate_digest)
        verify_upgrade(old, new, require_release=args.require_release)
    except OSError:
        print(json.dumps({"status": "BLOCKED", "reason": "APK_HASH_READ_FAILED"}, sort_keys=True))
        return 2
    except UpgradeRejected as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2

    print(json.dumps({
        "status": "APK_IDENTITIES_COMPATIBLE_FOR_IN_PLACE_UPGRADE",
        "package": new.package,
        "previous_version_code": old.version_code,
        "candidate_version_code": new.version_code,
        "signer_cert_sha256": new.signing_cert_sha256,
        "previous_apk_sha256": previous_digest,
        "candidate_apk_sha256": candidate_digest,
        "expected_candidate_sha256_verified": True,
        "expected_previous_sha256_verified": bool(args.expected_previous_sha256),
        "require_release": args.require_release,
        "device_installation_verified": False,
        "owner_authentication_verified": False,
        "play_console_accepted": False,
        "database_migration_verified": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
