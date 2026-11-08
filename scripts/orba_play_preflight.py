#!/usr/bin/env python3
"""Offline, read-only Google Play / ORBA preflight for KRAL Android sources.

Never connects to Play Console, reads credentials or declares payments approved.
Returns structured evidence rather than a fictional yes/no Play approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
SDK_REQUIRED = 36  # Play target API requirement as of 2026-08-31 for phone apps.


def _gradle_string(source: str, name: str) -> str | None:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*\"([^\"\n]+)\"", source)
    return match.group(1) if match else None


def _gradle_number(source: str, name: str) -> int | None:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*(\d+)", source)
    return int(match.group(1)) if match else None


def _finding(control: str, status: str, evidence: str) -> dict[str, str]:
    return {"control": control, "status": status, "evidence": evidence}


def inspect(root: Path, aab: Path | None = None) -> dict:
    """Only reads source files and an optional preexisting AAB; never executes builds."""
    root = Path(root).resolve()
    gradle_path = root / "app/build.gradle.kts"
    manifest_path = root / "app/src/main/AndroidManifest.xml"
    if not gradle_path.is_file() or not manifest_path.is_file():
        raise ValueError("Gradle and Android manifest must both exist")
    gradle = gradle_path.read_text(encoding="utf-8")
    manifest = ET.parse(manifest_path).getroot()
    package = _gradle_string(gradle, "applicationId")
    target = _gradle_number(gradle, "targetSdk")
    min_sdk = _gradle_number(gradle, "minSdk")
    version_code = _gradle_number(gradle, "versionCode")
    version_name = _gradle_string(gradle, "versionName")
    permissions = sorted({e.get(ANDROID_NS + "name", "") for e in manifest.findall("uses-permission")})
    findings = []
    findings.append(_finding("package_id", "PASS" if package else "BLOCKED", package or "applicationId missing"))
    findings.append(_finding("target_sdk", "PASS" if target is not None and target >= SDK_REQUIRED else "BLOCKED", f"targetSdk={target}; threshold={SDK_REQUIRED}"))
    findings.append(_finding("version", "PASS" if version_code and version_name else "BLOCKED", f"versionCode={version_code}, versionName={version_name}"))
    findings.append(_finding("manifest_permissions", "REVIEW", ", ".join(permissions) or "none"))
    release_match = re.search(r"\brelease\s*\{([^{}]*)\}", gradle)
    not_debuggable = bool(release_match and re.search(r"\bisDebuggable\s*=\s*false\b", release_match.group(1)))
    findings.append(_finding("release_non_debuggable", "PASS" if not_debuggable else "BLOCKED", "release isDebuggable=false" if not_debuggable else "Non-debuggable release not proven in source"))
    ads_present = "com.google.android.gms:play-services-ads" in gradle or "com.google.android.gms.ads" in gradle
    billing_present = "com.android.billingclient:billing" in gradle
    findings.append(_finding("admob_sdk", "SOURCE_PRESENT" if ads_present else "NOT_IMPLEMENTED", "Google Mobile Ads SDK dependency" if ads_present else "No Google Mobile Ads SDK dependency; no ad income readiness"))
    findings.append(_finding("play_billing_sdk", "SOURCE_PRESENT" if billing_present else "NOT_IMPLEMENTED", "Play Billing dependency" if billing_present else "No Play Billing dependency; does not bar free apps or paid-download apps"))
    model_path = root / "app/src/main/java/com/example/gptasistan/ModelGateway.kt"
    outbound_text = model_path.is_file() and "question" in model_path.read_text(encoding="utf-8")
    findings.append(_finding("data_safety_review", "REVIEW_REQUIRED", "User-entered question may leave device over HTTPS" if outbound_text else "Audit all data collection/sharing and backend flows"))
    if package and package.startswith("com.example."):
        findings.append(_finding("package_name_branding", "REVIEW", "com.example.* package; changing it can break update identity"))
    if aab is None:
        findings.append(_finding("signed_aab", "BLOCKED", "No release AAB supplied; no signing claim"))
    else:
        bundle = Path(aab).resolve()
        if not bundle.is_file() or bundle.suffix.lower() != ".aab":
            findings.append(_finding("signed_aab", "BLOCKED", "AAB path not a regular .aab file"))
        else:
            digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
            try:
            # Strict mode treats signer-related warnings (including unsigned entries) as a failure.
                checked = subprocess.run(["jarsigner", "-verify", "-strict", "-verbose", str(bundle)],
                                         text=True, capture_output=True, timeout=30, check=False)
                combined = (checked.stdout + checked.stderr).lower()
                valid = (checked.returncode == 0 and "jar verified" in combined
                         and "jar is unsigned" not in combined
                         and "unsigned entry" not in combined
                         and "unsigned entries" not in combined)
                findings.append(_finding("signed_aab", "JAR_VERIFIED" if valid else "BLOCKED",
                                         f"aab_sha256={digest}; JAR signature {'verified' if valid else 'not verified'}; Play signing key match NOT_CHECKED"))
            except (OSError, subprocess.TimeoutExpired):
                findings.append(_finding("signed_aab", "BLOCKED", f"aab_sha256={digest}; jarsigner unavailable or timed out"))
    external = [
        "ORBA Play Console identity, device, phone and app inventory",
        "Play App Signing enrollment and matching upload key",
        "Merchant/Google Payments verification and payout bank status",
        "AdMob publisher, app, app-ads.txt and payment verification",
        "Public privacy policy, support site, consent and Data safety declaration",
        "Store listing assets and production testing access",
        "Owner-approved pricing (free vs paid download, ads, digital purchases)",
        "Physical device and installed-package upgrade compatibility",
    ]
    return {
        "schema": "orba-play-preflight.v1", "mode": "READ_ONLY", "source": "local_gradle_manifest",
        "application_id": package, "version_name": version_name, "version_code": version_code,
        "target_sdk": target, "min_sdk": min_sdk, "findings": findings,
        "external_evidence": [{"control": x, "status": "NOT_CHECKED"} for x in external],
        "play_upload_approved": False, "revenue_ready": False,
        "conclusion": "BLOCKED_PENDING_SIGNED_RELEASE_AND_VERIFIED_CONSOLE",
        "note": "A local source audit cannot access or approve Play, AdMob or bank accounts.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--aab", type=Path, help="Optional existing AAB to verify with jarsigner")
    parser.add_argument("--output", type=Path, help="Optional local evidence JSON destination")
    parser.add_argument("--strict", action="store_true", help="Return exit 2 while release/console gates are not verified")
    args = parser.parse_args(argv)
    try:
        report = inspect(args.repo_root, args.aab)
    except (ValueError, ET.ParseError, OSError, UnicodeError) as exc:
        print(json.dumps({"schema": "orba-play-preflight.v1", "conclusion": "ERROR", "reason": type(exc).__name__}, indent=2), file=sys.stdout)
        return 1
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 2 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
