"""Offline structural gate for unsigned release-candidate Android App Bundles.

This is NOT Play signing or a Play Console check. The CI builder has no
upload key or Play credentials. A structurally healthy, unsigned AAB is a
test-only preflight artifact and cannot be uploaded as a signed release.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from server.play_distribution_preflight import source_from_repo, PreflightDenied

MAX_AAB_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_FILES = 10000
SIGNATURE_EXTENSIONS = frozenset((".SF", ".RSA", ".DSA", ".EC"))


class BundlePreflightDenied(ValueError):
    """Static error, no local path or user data embedded."""


def inspect_bundle(path: Path, *, require_unsigned=True) -> dict:
    """Check archive integrity, module layout and signature absence.

    This does not decode binary protobuf AndroidManifest.xml (and hence
    cannot attest the actual AAB applicationId). Debug APK identity is
    verified separately by the previous PR's aapt/apksigner checks.
    """
    if type(require_unsigned) is not bool or not require_unsigned:
        raise BundlePreflightDenied("UNSIGNED_CI_POLICY_REQUIRED")
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_AAB_BYTES:
            raise BundlePreflightDenied("BUNDLE_SIZE_INVALID")
        digest = hashlib.sha256()
        with path.open("rb") as input_file:
            while True:
                block = input_file.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        with zipfile.ZipFile(path, "r") as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_FILES:
                raise BundlePreflightDenied("BUNDLE_ENTRIES_INVALID")
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)):
                raise BundlePreflightDenied("BUNDLE_DUPLICATE_ENTRY")
            total = 0
            for entry in entries:
                name = entry.filename
                if (not name or name.startswith("/") or "\\" in name or
                        any(x in ("..", ".", "") for x in name.rstrip("/").split("/")) or
                        "\x00" in name or entry.file_size < 0):
                    raise BundlePreflightDenied("BUNDLE_UNSAFE_ENTRY")
                total += entry.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise BundlePreflightDenied("BUNDLE_EXPANSION_LIMIT")
                if (name.startswith("META-INF/") and name.upper().endswith(
                        tuple(SIGNATURE_EXTENSIONS))):
                    raise BundlePreflightDenied("UNEXPECTED_BUNDLE_SIGNATURE")
            required = (
                "BundleConfig.pb",
                "base/manifest/AndroidManifest.xml",
                "base/resources.pb",
            )
            if any(name not in names for name in required):
                raise BundlePreflightDenied("BUNDLE_REQUIRED_STRUCTURE_MISSING")
            if not any(re.fullmatch(r"base/dex/classes(?:\d+)?\.dex", x) for x in names):
                raise BundlePreflightDenied("BUNDLE_DEX_MISSING")
            # ZipFile.testzip checks CRC and decompresses every file.
            if archive.testzip() is not None:
                raise BundlePreflightDenied("BUNDLE_CRC_FAILED")
    except BundlePreflightDenied:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, EOFError):
        raise BundlePreflightDenied("BUNDLE_READ_OR_INTEGRITY_FAILED") from None
    return {
        "structure": "PASS",
        "signature": "UNSIGNED_CONFIRMED_BY_ARCHIVE_MARKERS",
        "release_upload_ready": False,
        "production": "HOLD",
        "bundle_sha256": digest.hexdigest(),
        "bundle_size_bytes": size,
        "android_bundle_manifest_package": "NOT_DECODED",
        "play_console_product_catalog": "NOT_VERIFIED",
        "play_console_signing": "NOT_VERIFIED",
        "device_installation": "NOT_TESTED",
        "real_google_play_payment": "NOT_TESTED",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline unsigned AAB structural preflight")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    try:
        source = source_from_repo(Path(args.repo_root))
        report = inspect_bundle(Path(args.bundle))
        report["source_application_id"] = source["package"]
        report["source_version_code"] = source["version_code"]
        print(json.dumps(report, sort_keys=True))
        return 0
    except (BundlePreflightDenied, PreflightDenied) as error:
        print(json.dumps({"structure": "FAIL", "production": "HOLD", "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
