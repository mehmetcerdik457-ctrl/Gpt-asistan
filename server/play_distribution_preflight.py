"""Read-only ORBA Play package/signing preflight. NEVER a production approval.

This checks source versus compiled DEBUG APK; Play Console/catalog/signing
account ownership cannot be proven offline. All successful reports say HOLD.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from server.play_entitlement_gate import PACKAGE as ENTITLEMENT
from server.play_google_api import PACKAGE as API_PACKAGE
from server.play_acknowledgement import PACKAGE as ACK_PACKAGE
from server.play_rtdn import PACKAGE as RTDN_PACKAGE
from server.play_voided_audit import PACKAGE as VOIDED_PACKAGE


class PreflightDenied(ValueError):
    """Fixed non-sensitive validation failure."""


def exactly(text, regex, error):
    found = re.findall(regex, text, flags=re.MULTILINE)
    if len(found) != 1:
        raise PreflightDenied(error)
    return found[0]


def source_identity(gradle, manifest, packages):
    if not isinstance(gradle, str) or not isinstance(manifest, str):
        raise PreflightDenied("SOURCE_INVALID")
    app = exactly(gradle, r'^\s*applicationId\s*=\s*"([^"]+)"',
                  "PACKAGE_AMBIGUOUS")
    name = exactly(gradle, r'^\s*versionName\s*=\s*"([^"]+)"',
                   "VERSION_AMBIGUOUS")
    code = int(exactly(gradle, r"^\s*versionCode\s*=\s*(\d+)\s*$",
                       "VERSION_CODE_AMBIGUOUS"))
    minimum = int(exactly(gradle, r"^\s*minSdk\s*=\s*(\d+)\s*$",
                          "MIN_SDK_AMBIGUOUS"))
    target = int(exactly(gradle, r"^\s*targetSdk\s*=\s*(\d+)\s*$",
                         "TARGET_SDK_AMBIGUOUS"))
    compile_sdk = int(exactly(gradle, r"^\s*compileSdk\s*=\s*(\d+)\s*$",
                              "COMPILE_SDK_AMBIGUOUS"))
    billing = exactly(gradle,
        r'^\s*implementation\("com\.android\.billingclient:billing:(\d+\.\d+\.\d+)"\)\s*$',
        "BILLING_VERSION_AMBIGUOUS")
    if (not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", app)
            or not isinstance(packages, dict) or len(packages) != 5
            or any(v != app for v in packages.values())):
        raise PreflightDenied("APP_SERVER_PACKAGE_MISMATCH")
    if not name or code <= 0 or not 23 <= minimum <= target <= compile_sdk <= 99:
        raise PreflightDenied("ANDROID_BUILD_POLICY_INVALID")
    try:
        root = ET.fromstring(manifest)
    except ET.ParseError:
        raise PreflightDenied("MANIFEST_INVALID") from None
    android = "{http://schemas.android.com/apk/res/android}"
    apps = root.findall("application")
    if len(apps) != 1:
        raise PreflightDenied("APPLICATION_MANIFEST_AMBIGUOUS")
    app_node = apps[0]
    if (app_node.get(android + "usesCleartextTraffic") != "false"
            or app_node.get(android + "allowBackup") != "false"):
        raise PreflightDenied("MANIFEST_TRANSPORT_OR_BACKUP_UNSAFE")
    perms = {node.get(android + "name")
             for node in root.findall("uses-permission")}
    if "android.permission.INTERNET" not in perms:
        raise PreflightDenied("INTERNET_PERMISSION_MISSING")
    return dict(package=app, version_name=name, version_code=code,
                min_sdk=minimum, target_sdk=target, billing=billing)


def source_from_repo(repo):
    try:
        root = Path(repo)
        gradle = (root / "app/build.gradle.kts").read_text("utf-8")
        manifest = (root / "app/src/main/AndroidManifest.xml").read_text("utf-8")
    except (OSError, UnicodeError):
        raise PreflightDenied("SOURCE_UNAVAILABLE") from None
    return source_identity(gradle, manifest, dict(
        entitlement=ENTITLEMENT, api=API_PACKAGE, acknowledge=ACK_PACKAGE,
        rtdn=RTDN_PACKAGE, voided=VOIDED_PACKAGE))


def debug_apk_identity(badging, signing, source):
    if not isinstance(badging, str) or not isinstance(signing, str):
        raise PreflightDenied("APK_REPORT_MISSING")
    packages = re.findall(
        r"(?m)^package:\s+name='([^']+)'\s+versionCode='([^']+)'\s+versionName='([^']+)'",
        badging)
    if len(packages) != 1 or packages[0] != (
        source["package"], str(source["version_code"]), source["version_name"]):
        raise PreflightDenied("COMPILED_APK_PACKAGE_MISMATCH")
    mins = re.findall(r"(?m)^sdkVersion:'(\d+)'$", badging)
    targets = re.findall(r"(?m)^targetSdkVersion:'(\d+)'$", badging)
    if len(mins) != 1 or len(targets) != 1 or (
            int(mins[0]), int(targets[0])) != (
            source["min_sdk"], source["target_sdk"]):
        raise PreflightDenied("COMPILED_APK_SDK_MISMATCH")
    if not re.search(r"(?m)^application-debuggable(?:\s|$)", badging):
        raise PreflightDenied("DEBUG_ARTIFACT_NOT_PROVEN")
    # apksigner 37+ reports 'V2 Signer:' or 'V3.0 Signer:' rather
    # than historical 'Signer #1'. Never accept contradictory signer keys.
    digest = re.findall(
        r"(?im)^(?:Signer #1|V[123](?:\.\d+)? Signer): "
        r"certificate SHA-256 digest:\s*([a-f0-9]{64})\s*$",
        signing)
    if not digest or len({x.lower() for x in digest}) != 1:
        raise PreflightDenied("APK_SIGNATURE_NOT_PROVEN")
    return dict(kind="DEBUG_APK", debug_certificate_sha256=digest[0].lower())


def hold_report(source, artifact=None):
    return dict(
        source_package_consistency="PASS",
        built_debug_apk_consistency="PASS" if artifact else "NOT_CHECKED",
        package=source["package"], version_code=source["version_code"],
        billing=source["billing"],
        production="HOLD",
        play_console_package="NOT_VERIFIED",
        play_subscription_catalog="NOT_VERIFIED",
        play_app_signing="NOT_VERIFIED",
        licensed_test_purchase="NOT_VERIFIED",
        google_pubsub_live="NOT_VERIFIED",
        reason="OFFLINE_SOURCE_AND_DEBUG_CHECKS_CANNOT_AUTHORIZE_PRODUCTION")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--apk-badging")
    parser.add_argument("--apk-signing-report")
    parser.add_argument("--expected-play-package")
    args = parser.parse_args(argv)
    try:
        source = source_from_repo(args.repo_root)
        if args.expected_play_package and args.expected_play_package != source["package"]:
            raise PreflightDenied("EXPECTED_PLAY_PACKAGE_MISMATCH")
        if bool(args.apk_badging) != bool(args.apk_signing_report):
            raise PreflightDenied("APK_REPORT_PAIR_REQUIRED")
        artifact = None
        if args.apk_badging:
            artifact = debug_apk_identity(
                Path(args.apk_badging).read_text("utf-8"),
                Path(args.apk_signing_report).read_text("utf-8"), source)
        print(json.dumps(hold_report(source, artifact), sort_keys=True))
        return 0
    except (PreflightDenied, OSError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, PreflightDenied) else "EVIDENCE_UNAVAILABLE"
        print(json.dumps(dict(production="HOLD", check="FAIL", reason=code)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
