#!/usr/bin/env python3
"""Verify pinned release APK/AAB signatures, matching manifests and universal ABIs."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ABIS = {"armeabi-v7a", "arm64-v8a", "x86", "x86_64"}
ANDROID_NS = "http://schemas.android.com/apk/res/android"
PACKAGE = "com.example.gptasistan.genesis"


def varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("AAB_MANIFEST_PROTO_TRUNCATED")
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError("AAB_MANIFEST_PROTO_VARINT_INVALID")


def fields(data):
    """Read bounded protobuf fields from AAPT2 Resources.proto XML messages."""
    offset = 0
    while offset < len(data):
        tag, offset = varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError("AAB_MANIFEST_PROTO_TAG_INVALID")
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire in (1, 2, 5):
            if wire == 2:
                size, offset = varint(data, offset)
            else:
                size = 8 if wire == 1 else 4
            end = offset + size
            if end > len(data):
                raise ValueError("AAB_MANIFEST_PROTO_TRUNCATED")
            value, offset = data[offset:end], end
        else:
            raise ValueError("AAB_MANIFEST_PROTO_WIRE_INVALID")
        yield number, value


def single(items, number, default=None):
    values = [value for key, value in items if key == number]
    if len(values) > 1:
        raise ValueError("AAB_MANIFEST_PROTO_DUPLICATE_FIELD")
    return values[0] if values else default


def element(node):
    data = single(list(fields(node)), 1)
    if data is None:
        return None
    items = list(fields(data))
    name = single(items, 3, b"").decode("utf-8")
    attrs = {}
    for number, raw in items:
        if number != 4:
            continue
        attr = list(fields(raw))
        key = (single(attr, 1, b"").decode("utf-8"), single(attr, 2, b"").decode("utf-8"))
        if key in attrs:
            raise ValueError("AAB_MANIFEST_ATTRIBUTE_DUPLICATE")
        value = single(attr, 3, b"").decode("utf-8")
        compiled = single(attr, 6)
        if compiled is not None:
            item = list(fields(compiled))
            primitive = single(item, 7)
            string = single(item, 2)
            if primitive is not None:
                prim = list(fields(primitive))
                boolean = single(prim, 8)
                integer = single(prim, 6, single(prim, 7))
                if boolean is not None:
                    value = "true" if boolean else "false"
                elif integer is not None:
                    value = str(integer)
            elif string is not None:
                value = single(list(fields(string)), 1, b"").decode("utf-8")
        attrs[key] = value
    return name, attrs, [value for key, value in items if key == 5]


def bundle_manifest(data):
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("AAB_MANIFEST_SIZE_LIMIT")
    root = element(data)
    if root is None or root[0] != "manifest":
        raise ValueError("AAB_MANIFEST_ROOT_INVALID")
    _, attrs, children = root
    apps, sdks = [], []
    for child in children:
        parsed = element(child)
        if parsed and parsed[0] == "application":
            apps.append(parsed[1])
        if parsed and parsed[0] == "uses-sdk":
            sdks.append(parsed[1])
    if len(apps) != 1 or len(sdks) != 1:
        raise ValueError("AAB_MANIFEST_ELEMENTS_INVALID")
    debug = apps[0].get((ANDROID_NS, "debuggable"), "false")
    if debug not in ("false", "true"):
        raise ValueError("AAB_DEBUGGABLE_INVALID")
    return {"package": attrs.get(("", "package")),
            "version_code": int(attrs[(ANDROID_NS, "versionCode")]),
            "version_name": attrs[(ANDROID_NS, "versionName")],
            "min_sdk": int(sdks[0][(ANDROID_NS, "minSdkVersion")]),
            "target_sdk": int(sdks[0][(ANDROID_NS, "targetSdkVersion")]),
            "debuggable": debug == "true"}


def command(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=90).stdout


def field(pattern, text):
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError("RELEASE_APK_METADATA_MISSING")
    return match.group(1)


def verify_bundle_signature(bundle, expected):
    # A pinned self-signed certificate is expected; bit 4 is the only allowed
    # strict-verification warning. Unsigned entries (16), wrong signatures and
    # all other strict errors fail. Locale is fixed for the verified marker.
    result = subprocess.run(["jarsigner", "-J-Duser.language=en", "-J-Duser.country=US",
                             "-verify", "-strict", str(bundle)], capture_output=True, text=True, timeout=90)
    if result.returncode not in (0, 4) or not re.search(r"(?m)^jar verified\.", result.stdout):
        raise ValueError("RELEASE_AAB_SIGNATURE_INVALID")
    certs = command("keytool", "-J-Duser.language=en", "-J-Duser.country=US",
                    "-printcert", "-jarfile", str(bundle), "-rfc")
    if len(re.findall(r"(?m)^Signer #", certs)) != 1:
        raise ValueError("RELEASE_AAB_SIGNER_AMBIGUOUS")
    blocks = re.findall(r"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----", certs, re.S)
    if not blocks or hashlib.sha256(base64.b64decode("".join(blocks[0].split()), validate=True)).hexdigest() != expected:
        raise ValueError("RELEASE_AAB_SIGNER_PIN_MISMATCH")


def archive_content(path, *, bundle=False):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or sum(item.file_size for item in archive.infolist()) > 256 * 1024 * 1024:
            raise ValueError("RELEASE_ARCHIVE_INVALID")
        if archive.testzip() is not None:
            raise ValueError("RELEASE_ARCHIVE_CORRUPT")
        prefix = "base/" if bundle else ""
        abis = {name.split("/")[2 if bundle else 1] for name in names
                if name.startswith(prefix + "lib/") and name.endswith(".so")}
        dex_prefix = "base/dex/" if bundle else ""
        dex = {name.removeprefix(dex_prefix): hashlib.sha256(archive.read(name)).hexdigest()
               for name in names if re.fullmatch(re.escape(dex_prefix) + r"classes(?:[0-9]+)?\.dex", name)}
        manifest = bundle_manifest(archive.read("base/manifest/AndroidManifest.xml")) if bundle else None
        return abis, dex, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--signing-report", required=True, type=Path)
    parser.add_argument("--sdk", type=Path, default=os.environ.get("ANDROID_HOME"))
    parser.add_argument("--build-tools", default="36.0.0")
    args = parser.parse_args()
    sha = command("git", "rev-parse", "HEAD").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_sha) or args.expected_sha != sha:
        raise ValueError("SOURCE_SHA_MISMATCH")
    report = json.loads(args.signing_report.read_text())
    config = json.loads(Path("config/android-owner-signing.json").read_text())
    expected = config["certificate_sha256"]
    if (report.get("source_commit") != sha or report.get("owner_signing_verified") is not True
            or report.get("release_apk_aab_verified") is not True
            or report.get("status") != "OWNER_SIGNER_PIN_VERIFIED"
            or report.get("expected_certificate_sha256") != expected
            or report.get("actual_certificate_sha256") != expected):
        raise ValueError("RELEASE_SIGNING_REPORT_INVALID")
    if not args.sdk:
        parser.error("--sdk or ANDROID_HOME is required")
    sdk = args.sdk / "build-tools" / args.build_tools
    badging = command(str(sdk / "aapt"), "dump", "badging", str(args.apk))
    signature = command(str(sdk / "apksigner"), "verify", "--verbose", "--print-certs", str(args.apk))
    if re.findall(r"(?m)^Signer #\d+ certificate SHA-256 digest:\s*(\S+)", signature) != [expected]:
        raise ValueError("RELEASE_APK_SIGNER_PIN_MISMATCH")
    manifest = {"package": field(r"^package: name='([^']+)'", badging),
                "version_code": int(field(r"^package: .*versionCode='([^']+)'", badging)),
                "version_name": field(r"^package: .*versionName='([^']+)'", badging),
                "min_sdk": int(field(r"^sdkVersion:'([^']+)'", badging)),
                "target_sdk": int(field(r"^targetSdkVersion:'([^']+)'", badging)),
                "debuggable": "application-debuggable" in badging}
    if manifest["package"] != PACKAGE or manifest["debuggable"] or "split=" in badging.splitlines()[0]:
        raise ValueError("RELEASE_APK_IDENTITY_INVALID")
    apk_abis, apk_dex, _ = archive_content(args.apk)
    bundle_abis, bundle_dex, aab_manifest = archive_content(args.bundle, bundle=True)
    if apk_abis != ABIS or bundle_abis != ABIS:
        raise ValueError("RELEASE_UNIVERSAL_ABIS_MISSING")
    if not apk_dex or apk_dex != bundle_dex or manifest != aab_manifest:
        raise ValueError("RELEASE_APK_AAB_CONTENT_MISMATCH")
    verify_bundle_signature(args.bundle, expected)
    artifacts = [{"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "size_bytes": path.stat().st_size} for path in (args.apk, args.bundle)]
    metadata = dict(manifest, source_commit=sha, exact_source_head_verified=True,
                    signing_status="OWNER_SIGNER_PIN_VERIFIED", signer_certificate_sha256=expected,
                    native_abis=sorted(ABIS), standalone_apk=True, apk_aab_manifest_dex_match=True,
                    signature_verified=True, artifacts=artifacts, physical_device_tested=False,
                    previous_install_upgrade_verified=False, play_console_validated=False,
                    github_run_id=os.environ.get("GITHUB_RUN_ID"))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "release-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (args.output / "RELEASE-SHA256SUMS").write_text("".join(f"{item['sha256']}  {item['file']}\n" for item in artifacts))
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
