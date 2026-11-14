"""Fail-closed device-profile extraction audit for bundletool .apks archives.

Profiles are synthetic emulator/Android configuration examples; successful
extraction is NOT physical compatibility testing, Play signing or revenue.
Actual APK files are checked using installed Android SDK aapt/apksigner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from server.play_distribution_preflight import source_from_repo, PreflightDenied

PROFILES = {
    "api26-arm64": {
        "supportedAbis": ["arm64-v8a", "armeabi-v7a"],
        "supportedLocales": ["tr", "en"],
        "screenDensity": 420, "sdkVersion": 26},
    "api30-x86_64": {
        "supportedAbis": ["x86_64", "x86"],
        "supportedLocales": ["tr", "en"],
        "screenDensity": 320, "sdkVersion": 30},
    "api36-arm64": {
        "supportedAbis": ["arm64-v8a", "armeabi-v7a"],
        "supportedLocales": ["tr", "en"],
        "screenDensity": 480, "sdkVersion": 36},
    "api36-x86_64": {
        "supportedAbis": ["x86_64", "x86"],
        "supportedLocales": ["tr", "en"],
        "screenDensity": 320, "sdkVersion": 36},
}

MAX_APKSET_BYTES = 110 * 1024 * 1024
MAX_EXPANDED_BYTES = 320 * 1024 * 1024
MAX_ENTRIES = 10000
MAX_EXTRACTED_APKS = 150


class ApkSetRejected(ValueError):
    """An intentionally static error: no token/path/vendor data leaked."""


def check_profile_json(profile_name, raw):
    if profile_name not in PROFILES:
        raise ApkSetRejected("UNKNOWN_SYNTHETIC_PROFILE")
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        raise ApkSetRejected("PROFILE_JSON_INVALID") from None
    if type(decoded) is not dict or decoded != PROFILES[profile_name]:
        raise ApkSetRejected("PROFILE_SPEC_MISMATCH")
    return decoded


def inspect_apks_archive(path):
    """Check container ZIP and TOC, not a substitute for bundletool parsing."""
    try:
        p = Path(path)
        size = p.stat().st_size
        if not 0 < size <= MAX_APKSET_BYTES:
            raise ApkSetRejected("APK_SET_SIZE_INVALID")
        with zipfile.ZipFile(p) as archive:
            info = archive.infolist()
            if not info or len(info) > MAX_ENTRIES:
                raise ApkSetRejected("APK_SET_ENTRY_COUNT_INVALID")
            names = [i.filename for i in info]
            if len(set(names)) != len(names):
                raise ApkSetRejected("APK_SET_DUPLICATE_ENTRY")
            total = 0
            for entry in info:
                name = entry.filename
                if (not name or name.startswith("/") or "\\" in name or
                        "\x00" in name or
                        any(part in (".", "..", "") for part in name.rstrip("/").split("/"))):
                    raise ApkSetRejected("APK_SET_UNSAFE_ENTRY")
                total += entry.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise ApkSetRejected("APK_SET_EXPANSION_LIMIT")
            if ("toc.pb" not in names or
                    not any(name.endswith(".apk") for name in names)):
                raise ApkSetRejected("APK_SET_STRUCTURE_MISSING")
            if archive.testzip() is not None:
                raise ApkSetRejected("APK_SET_CRC_INVALID")
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return {"sha256": h.hexdigest(), "byte_size": size}
    except ApkSetRejected:
        raise
    except (OSError, zipfile.BadZipFile, EOFError, RuntimeError, ValueError):
        raise ApkSetRejected("APK_SET_READ_FAILED") from None


def _run(command, runner):
    try:
        response = runner(command, capture_output=True, text=True,
                          timeout=25, check=True)
        output = response.stdout
        if not isinstance(output, str) or len(output) > 256000:
            raise ValueError()
        return output
    except (OSError, ValueError, subprocess.SubprocessError):
        raise ApkSetRejected("ANDROID_SDK_INSPECTION_FAILED") from None


def _signature(output):
    digests = re.findall(
        r"(?im)^(?:Signer #1 certificate|V[123](?:\.\d+)? Signer: certificate) "
        r"SHA-256 digest:\s*([a-f0-9]{64})\s*$", output)
    if not digests or len({s.lower() for s in digests}) != 1:
        raise ApkSetRejected("SPLIT_APK_SIGNER_INVALID")
    return digests[0].lower()


def _base_badging(badging, source):
    packages = re.findall(
        r"(?m)^package:\s+name='([^']+)'\s+versionCode='([^']+)'\s+versionName='([^']+)'",
        badging)
    if len(packages) != 1 or packages[0] != (
            source["package"], str(source["version_code"]), source["version_name"]):
        raise ApkSetRejected("SPLIT_APK_PACKAGE_MISMATCH")
    minimum = re.findall(r"(?m)^sdkVersion:'(\d+)'$", badging)
    target = re.findall(r"(?m)^targetSdkVersion:'(\d+)'$", badging)
    if len(minimum) != 1 or len(target) != 1 or (
            int(minimum[0]), int(target[0])) != (
            source["min_sdk"], source["target_sdk"]):
        raise ApkSetRejected("SPLIT_APK_SDK_MISMATCH")
    if re.search(r"(?m)^application-debuggable(?:\s|$)", badging):
        raise ApkSetRejected("SPLIT_APK_DEBUGGABLE_DENIED")


def inspect_extractions(*, root, source, aapt, apksigner,
                        runner=subprocess.run):
    if (not isinstance(source, dict) or not isinstance(source.get("package"), str)
            or not isinstance(aapt, str) or not aapt
            or not isinstance(apksigner, str) or not apksigner):
        raise ApkSetRejected("APK_INSPECTION_CONFIG_INVALID")
    out = {}
    cert = None
    for profile, spec in PROFILES.items():
        folder = Path(root) / profile
        if not folder.is_dir():
            raise ApkSetRejected("PROFILE_EXTRACTION_MISSING")
        files = sorted(folder.rglob("*.apk"))
        if not 1 <= len(files) <= MAX_EXTRACTED_APKS:
            raise ApkSetRejected("PROFILE_APK_COUNT_INVALID")
        for f in files:
            if not f.is_file() or f.is_symlink() or f.stat().st_size == 0:
                raise ApkSetRejected("PROFILE_APK_FILE_INVALID")
            s = _signature(_run([
                apksigner, "verify", "--min-sdk-version", str(source["min_sdk"]),
                "--print-certs", str(f)], runner))
            if cert is None:
                cert = s
            elif cert != s:
                raise ApkSetRejected("APK_SET_SIGNER_CONFLICT")
        # bundletool may rename the output APKs. Detect the one actual
        # unqualified BASE/standalone by its *compiled package manifest*,
        # never a presumed filename. Config-only split has 'split=...'.
        base_badgings = []
        for f in files:
            badging = _run([aapt, "dump", "badging", str(f)], runner)
            package_line = next(
                (line for line in badging.splitlines()
                 if line.startswith("package: ")), "")
            if not package_line:
                raise ApkSetRejected("SPLIT_APK_PACKAGE_MISMATCH")
            if not re.search(
                    r"^package:\s+name='" + re.escape(source["package"]) +
                    r"'(?:\s|$)", package_line):
                raise ApkSetRejected("SPLIT_APK_PACKAGE_MISMATCH")
            if not re.search(r"\bsplit='[^']+'", package_line):
                base_badgings.append(badging)
        if len(base_badgings) != 1:
            raise ApkSetRejected("PROFILE_BASE_APK_MISSING")
        _base_badging(base_badgings[0], source)
        if spec["sdkVersion"] < source["min_sdk"]:
            raise ApkSetRejected("PROFILE_BELOW_MIN_SDK")
        out[profile] = {"apk_count": len(files), "sdk_version": spec["sdkVersion"],
                        "package": source["package"],
                        "selection": "PASS"}
    if cert is None:
        raise ApkSetRejected("APK_SET_SIGNER_MISSING")
    return {"profiles": out, "test_signer_sha256": cert}


def run_preflight(*, repo_root, apkset_path, profile_dir, extracts_root,
                  aapt, apksigner, runner=subprocess.run):
    source = source_from_repo(Path(repo_root))
    archive = inspect_apks_archive(apkset_path)
    for name in PROFILES:
        try:
            raw = (Path(profile_dir) / (name + ".json")).read_text("utf-8")
        except (OSError, UnicodeError):
            raise ApkSetRejected("PROFILE_FILE_MISSING") from None
        check_profile_json(name, raw)
    extracted = inspect_extractions(root=extracts_root, source=source,
                                    aapt=aapt, apksigner=apksigner, runner=runner)
    return {
        "device_profile_extractions": "PASS",
        "apk_set_sha256": archive["sha256"],
        "apk_set_bytes": archive["byte_size"],
        "profile_results": extracted["profiles"],
        "test_signer_sha256": extracted["test_signer_sha256"],
        "signing_purpose": "EPHEMERAL_LOCAL_TEST_ONLY_NOT_PLAY",
        "real_device_installation": "NOT_TESTED",
        "android_emulator_execution": "NOT_TESTED",
        "real_google_play_distribution": "NOT_TESTED",
        "release_upload_ready": False,
        "production": "HOLD",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--apks", required=True)
    parser.add_argument("--profile-dir", required=True)
    parser.add_argument("--extracts-root", required=True)
    parser.add_argument("--aapt", required=True)
    parser.add_argument("--apksigner", required=True)
    args = parser.parse_args(argv)
    try:
        report = run_preflight(
            repo_root=args.repo_root, apkset_path=args.apks,
            profile_dir=args.profile_dir, extracts_root=args.extracts_root,
            aapt=args.aapt, apksigner=args.apksigner)
        print(json.dumps(report, sort_keys=True))
        return 0
    except (ApkSetRejected, PreflightDenied) as e:
        print(json.dumps({"device_profile_extractions": "FAIL",
                          "production": "HOLD", "reason": str(e)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
