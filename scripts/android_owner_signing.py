#!/usr/bin/env python3
"""Use an existing, pinned owner keystore only on the authorized push branch.

No key generation, key rotation, upload of credentials, or device operation.
PR builds remain explicitly marked as ephemeral-debug-only. Missing credentials
produce a public BLOCKED signing report; functional debug tests may still run.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

SECRET_NAMES = ("ANDROID_KEYSTORE_BASE64", "ANDROID_KEY_ALIAS",
                "ANDROID_KEY_PASSWORD", "ANDROID_STORE_PASSWORD")
MAX_KEYSTORE_BYTES = 6 * 1024 * 1024


class SigningRejected(ValueError):
    pass


def trusted_context(env, config):
    return (env.get("GITHUB_EVENT_NAME") == "push"
            and env.get("GITHUB_REPOSITORY") == config["repository"]
            and env.get("GITHUB_REF") == "refs/heads/" + config["trusted_branch"]
            and env.get("GITHUB_ACTOR") == config["actor"])


def signer_digest(output):
    values = re.findall(r"(?m)^Signer #([1-9][0-9]*) certificate SHA-256 digest:\s*([0-9a-fA-F]{64})\s*$", output)
    if len(values) != 1 or values[0][0] != "1":
        raise SigningRejected("OWNER_APK_SIGNER_MISSING_OR_AMBIGUOUS")
    return values[0][1].lower()


def tool(argv, env, runner):
    try:
        return runner(argv, env=env, check=True, capture_output=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        # Never put command arguments, keystore output or tool stderr in a log.
        raise SigningRejected("OWNER_SIGNING_TOOL_FAILED") from None


@contextmanager
def release_keystore(config, env, runner):
    """Decode an existing identity only after the caller has checked its event."""
    expected = config["certificate_sha256"]
    raw = env["ANDROID_KEYSTORE_BASE64"]
    if len(raw) > MAX_KEYSTORE_BYTES * 2:
        raise SigningRejected("OWNER_KEYSTORE_SIZE_LIMIT")
    try:
        decoded = base64.b64decode("".join(raw.split()), validate=True)
    except (ValueError, TypeError):
        raise SigningRejected("OWNER_KEYSTORE_ENCODING_INVALID") from None
    if not decoded or len(decoded) > MAX_KEYSTORE_BYTES:
        raise SigningRejected("OWNER_KEYSTORE_SIZE_LIMIT")
    temp_root = Path(env["RUNNER_TEMP"]).resolve()
    workspace = Path(env["GITHUB_WORKSPACE"]).resolve()
    if temp_root == workspace or workspace in temp_root.parents:
        raise SigningRejected("OWNER_KEYSTORE_MUST_STAY_OUTSIDE_WORKSPACE")
    with tempfile.TemporaryDirectory(prefix="kral-release-signing-", dir=temp_root) as folder:
        root = Path(folder)
        keystore = root / "owner.keystore"
        with keystore.open("xb") as handle:
            os.chmod(keystore, 0o600)
            handle.write(decoded)
        certificate = tool(["keytool", "-exportcert", "-keystore", str(keystore),
                            "-alias", env["ANDROID_KEY_ALIAS"],
                            "-storepass:env", "ANDROID_STORE_PASSWORD"], env, runner)
        if not hmac.compare_digest(hashlib.sha256(certificate).hexdigest(), expected):
            raise SigningRejected("OWNER_KEYSTORE_CERT_PIN_MISMATCH")
        yield root, keystore


def sign_release(apk, bundle, config, env, apksigner, *, public_only=False, runner=subprocess.run):
    """Sign the release APK and AAB with the same existing pinned owner key.

    Every output stays untouched until both staged signatures verify. The AAB
    uses strict JAR verification with the pinned identity as its trust source,
    which rejects unsigned entries and an unexpected signing alias.
    """
    expected = config["certificate_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SigningRejected("OWNER_CERT_PIN_INVALID")
    report = {"status": "BLOCKED_RELEASE_UNTRUSTED_EVENT", "owner_signing_verified": False,
              "expected_certificate_sha256": expected, "new_key_created": False,
              "previous_install_upgrade_verified": False, "release_apk_aab_verified": False}
    release_config = dict(config, trusted_branch=config.get("release_branch", "main"))
    if public_only or not trusted_context(env, release_config):
        return report
    missing = [name for name in SECRET_NAMES if not env.get(name)]
    if missing:
        return dict(report, status="BLOCKED_OWNER_SECRETS_MISSING", missing_secret_names=missing)
    if (not apk or not bundle or not apk.is_file() or apk.is_symlink() or apk.suffix != ".apk"
            or not bundle.is_file() or bundle.is_symlink() or bundle.suffix != ".aab"
            or apk.resolve() == bundle.resolve()):
        raise SigningRejected("OWNER_RELEASE_INPUT_INVALID")
    with release_keystore(config, env, runner) as (root, keystore):
        signed_apk, signed_bundle = root / "signed.apk", root / "signed.aab"
        tool([apksigner, "sign", "--ks", str(keystore),
              "--ks-key-alias", env["ANDROID_KEY_ALIAS"],
              "--ks-pass", "env:ANDROID_STORE_PASSWORD", "--key-pass", "env:ANDROID_KEY_PASSWORD",
              "--v4-signing-enabled", "false", "--out", str(signed_apk), str(apk)], env, runner)
        verified = tool([apksigner, "verify", "--verbose", "--print-certs", str(signed_apk)], env, runner)
        if not hmac.compare_digest(signer_digest(verified.decode("utf-8")), expected):
            raise SigningRejected("OWNER_SIGNED_APK_CERT_MISMATCH")
        tool(["jarsigner", "-keystore", str(keystore), "-storepass:env", "ANDROID_STORE_PASSWORD",
              "-keypass:env", "ANDROID_KEY_PASSWORD", "-digestalg", "SHA-256",
              "-signedjar", str(signed_bundle), str(bundle), env["ANDROID_KEY_ALIAS"]], env, runner)
        tool(["jarsigner", "-verify", "-strict", "-keystore", str(keystore),
              "-storepass:env", "ANDROID_STORE_PASSWORD", str(signed_bundle),
              env["ANDROID_KEY_ALIAS"]], env, runner)
        shutil.copyfile(signed_apk, apk)
        shutil.copyfile(signed_bundle, bundle)
    return dict(report, status="OWNER_SIGNER_PIN_VERIFIED", owner_signing_verified=True,
                actual_certificate_sha256=expected, release_apk_aab_verified=True,
                signed_apks=[apk.name], signed_bundles=[bundle.name])


def sign_existing(apks, config, env, apksigner, *, public_only=False, runner=subprocess.run):
    expected = config["certificate_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SigningRejected("OWNER_CERT_PIN_INVALID")
    report = {"status": "DEBUG_ONLY_UNTRUSTED_EVENT", "owner_signing_verified": False,
              "expected_certificate_sha256": expected,
              "new_key_created": False, "previous_install_upgrade_verified": False}
    # Do not even read the secret environment fields for a PR or another actor/ref.
    if public_only or not trusted_context(env, config):
        return report
    missing = [name for name in SECRET_NAMES if not env.get(name)]
    if missing:
        return dict(report, status="BLOCKED_OWNER_SECRETS_MISSING", missing_secret_names=missing)
    raw = env["ANDROID_KEYSTORE_BASE64"]
    if len(raw) > MAX_KEYSTORE_BYTES * 2:
        raise SigningRejected("OWNER_KEYSTORE_SIZE_LIMIT")
    try:
        decoded = base64.b64decode("".join(raw.split()), validate=True)
    except (ValueError, TypeError):
        raise SigningRejected("OWNER_KEYSTORE_ENCODING_INVALID") from None
    if not decoded or len(decoded) > MAX_KEYSTORE_BYTES:
        raise SigningRejected("OWNER_KEYSTORE_SIZE_LIMIT")
    temp_root = Path(env["RUNNER_TEMP"]).resolve()
    workspace = Path(env["GITHUB_WORKSPACE"]).resolve()
    if temp_root == workspace or workspace in temp_root.parents:
        raise SigningRejected("OWNER_KEYSTORE_MUST_STAY_OUTSIDE_WORKSPACE")
    if len(apks) != 2 or len({p.resolve() for p in apks}) != 2 or any(
        not p.is_file() or p.is_symlink() or p.suffix != ".apk" for p in apks
    ):
        raise SigningRejected("OWNER_APK_INPUT_INVALID")
    with tempfile.TemporaryDirectory(prefix="kral-owner-signing-", dir=temp_root) as folder:
        root = Path(folder)
        keystore = root / "owner.keystore"
        with keystore.open("xb") as handle:
            os.chmod(keystore, 0o600)
            handle.write(decoded)
        certificate = tool(["keytool", "-exportcert", "-keystore", str(keystore),
                            "-alias", env["ANDROID_KEY_ALIAS"],
                            "-storepass:env", "ANDROID_STORE_PASSWORD"], env, runner)
        if not hmac.compare_digest(hashlib.sha256(certificate).hexdigest(), expected):
            raise SigningRejected("OWNER_KEYSTORE_CERT_PIN_MISMATCH")
        staged = []
        for index, apk in enumerate(apks):
            signed = root / f"signed-{index}.apk"
            tool([apksigner, "sign", "--ks", str(keystore),
                  "--ks-key-alias", env["ANDROID_KEY_ALIAS"],
                  "--ks-pass", "env:ANDROID_STORE_PASSWORD", "--key-pass", "env:ANDROID_KEY_PASSWORD",
                  "--v4-signing-enabled", "false", "--out", str(signed), str(apk)], env, runner)
            verified = tool([apksigner, "verify", "--verbose", "--print-certs", str(signed)], env, runner)
            if not hmac.compare_digest(signer_digest(verified.decode("utf-8")), expected):
                raise SigningRejected("OWNER_SIGNED_APK_CERT_MISMATCH")
            staged.append((signed, apk))
        # Both signatures must validate before replacing either staged build output.
        for signed, apk in staged:
            shutil.copyfile(signed, apk)
    return dict(report, status="OWNER_SIGNER_PIN_VERIFIED", owner_signing_verified=True,
                actual_certificate_sha256=expected, signed_apks=[p.name for p in apks])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/android-owner-signing.json"))
    parser.add_argument("--apk", action="append", type=Path, default=[])
    parser.add_argument("--release-apk", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--apksigner", default="apksigner")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-only", action="store_true")
    parser.add_argument("--require-owner", action="store_true", help="Fail instead of delivering an unsigned release")
    args = parser.parse_args()
    if (args.release_apk is not None or args.bundle is not None) and (
        args.release_apk is None or args.bundle is None or args.apk
    ):
        parser.error("Use --release-apk and --bundle together, without --apk")
    try:
        config = json.loads(args.config.read_text())
        if args.release_apk:
            report = sign_release(args.release_apk, args.bundle, config, os.environ,
                                  args.apksigner, public_only=args.public_only)
        else:
            report = sign_existing(args.apk, config, os.environ, args.apksigner, public_only=args.public_only)
        exit_code = int(args.require_owner and not report["owner_signing_verified"])
    except SigningRejected as error:
        report = {"status": "BLOCKED", "reason": str(error), "owner_signing_verified": False,
                  "new_key_created": False, "previous_install_upgrade_verified": False}
        exit_code = 1
    report.update(source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                  github_run_id=os.environ.get("GITHUB_RUN_ID"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
