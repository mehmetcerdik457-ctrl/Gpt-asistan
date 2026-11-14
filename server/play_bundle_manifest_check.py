"""Validate ACTUAL binary AAB manifest decoded by pinned official bundletool.

Source-only Gradle and debug APK checks cannot prove the release AAB package.
This tool compares decoded BASE manifest identity and security policy against
repo source and never asserts Play Console registration/signing.
"""
from __future__ import annotations
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from server.play_distribution_preflight import source_from_repo, PreflightDenied

ANDROID = "{http://schemas.android.com/apk/res/android}"
MAX_MANIFEST_BYTES = 512 * 1024


class BundleManifestRejected(ValueError):
    """Fixed non-sensitive error, no arbitrary manifest contents returned."""


def inspect_manifest(decoded_xml: str, source: dict) -> dict:
    if not isinstance(decoded_xml, str) or not 0 < len(decoded_xml.encode("utf-8")) <= MAX_MANIFEST_BYTES:
        raise BundleManifestRejected("AAB_MANIFEST_SIZE_INVALID")
    if "<!DOCTYPE" in decoded_xml.upper() or "<!ENTITY" in decoded_xml.upper():
        raise BundleManifestRejected("AAB_MANIFEST_EXTERNAL_ENTITY_DENIED")
    if not isinstance(source, dict) or not isinstance(source.get("package"), str):
        raise BundleManifestRejected("AAB_SOURCE_IDENTITY_INVALID")
    try:
        root = ET.fromstring(decoded_xml)
    except (ET.ParseError, ValueError):
        raise BundleManifestRejected("AAB_MANIFEST_DECODE_INVALID") from None
    if root.tag != "manifest" or root.get("package") != source["package"]:
        raise BundleManifestRejected("AAB_PACKAGE_MISMATCH")
    if root.get(ANDROID + "versionCode") != str(source["version_code"]):
        raise BundleManifestRejected("AAB_VERSION_CODE_MISMATCH")
    if root.get(ANDROID + "versionName") != source["version_name"]:
        raise BundleManifestRejected("AAB_VERSION_NAME_MISMATCH")
    sdk = root.findall("uses-sdk")
    if len(sdk) != 1:
        raise BundleManifestRejected("AAB_SDK_DECLARATION_AMBIGUOUS")
    if (sdk[0].get(ANDROID + "minSdkVersion") != str(source["min_sdk"]) or
            sdk[0].get(ANDROID + "targetSdkVersion") != str(source["target_sdk"])):
        raise BundleManifestRejected("AAB_SDK_BOUND_MISMATCH")
    apps = root.findall("application")
    if len(apps) != 1:
        raise BundleManifestRejected("AAB_APPLICATION_AMBIGUOUS")
    app = apps[0]
    if app.get(ANDROID + "debuggable") not in (None, "false"):
        raise BundleManifestRejected("AAB_DEBUGGABLE_RELEASE_DENIED")
    if (app.get(ANDROID + "usesCleartextTraffic") != "false" or
            app.get(ANDROID + "allowBackup") != "false"):
        raise BundleManifestRejected("AAB_SECURITY_FLAGS_INVALID")
    permissions = {x.get(ANDROID + "name") for x in root.findall("uses-permission")}
    if "android.permission.INTERNET" not in permissions:
        raise BundleManifestRejected("AAB_INTERNET_PERMISSION_MISSING")
    return {
        "decoded_bundle_manifest": "PASS",
        "release_variant_package": source["package"],
        "release_variant_version_code": source["version_code"],
        "release_variant_version_name": source["version_name"],
        "release_variant_min_sdk": source["min_sdk"],
        "release_variant_target_sdk": source["target_sdk"],
        "release_variant_debuggable": False,
        "release_upload_ready": False,
        "production": "HOLD",
        "play_console_registration": "NOT_VERIFIED",
        "upload_and_app_signing": "NOT_VERIFIED",
        "live_payments": "NOT_TESTED",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Official bundletool decoded manifest guard")
    p.add_argument("--repo-root", default=".")
    p.add_argument("--decoded-manifest", required=True)
    a = p.parse_args(argv)
    try:
        src = source_from_repo(Path(a.repo_root))
        path = Path(a.decoded_manifest)
        if not 0 < path.stat().st_size <= MAX_MANIFEST_BYTES:
            raise BundleManifestRejected("AAB_MANIFEST_SIZE_INVALID")
        xml = path.read_text("utf-8")
        report = inspect_manifest(xml, src)
        print(json.dumps(report, sort_keys=True))
        return 0
    except (BundleManifestRejected, PreflightDenied, OSError, UnicodeError) as exc:
        error = str(exc) if isinstance(exc, (BundleManifestRejected, PreflightDenied)) else "AAB_MANIFEST_UNAVAILABLE"
        print(json.dumps({"decoded_bundle_manifest": "FAIL", "production": "HOLD",
                          "reason": error}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
