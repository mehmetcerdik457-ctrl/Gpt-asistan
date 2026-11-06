#!/usr/bin/env python3
"""Validate fresh-install encrypted-backup evidence; never handle a backup password.

The two native test phases run on the same disposable emulator, separated by
complete application/test-package removal. This does not prove a second device
or physical-phone behavior, and synthetic parser fixtures are not device runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct

PACKAGE = "com.example.gptasistan.genesis"
TEST_PACKAGE = PACKAGE + ".test"
TEST_CLASS = "com.example.gptasistan.BackupInstallationTest"
TEST_METHOD = "encryptedBackupRestoresAfterFreshInstallation"
MAX_BACKUP_BYTES = 16 * 1024 * 1024
MAX_APK_BYTES = 256 * 1024 * 1024
HASH = re.compile(r"[0-9a-f]{64}\Z")
SOURCE = re.compile(r"[0-9a-f]{40}\Z")
COMMON_FLAGS = {"kral_backup_archive_encrypted", "kral_backup_encrypted_db_verified"}
PHASE_FLAGS = {
    "export": {"kral_backup_source_installation_fresh", "kral_backup_source_key_created",
               "kral_backup_source_rows_verified"},
    "restore": {"kral_backup_target_installation_fresh", "kral_backup_target_key_created",
                "kral_backup_restore_verified", "kral_backup_reopen_verified"},
}


def read_bytes(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file() or not 0 <= path.stat().st_size <= maximum:
        raise ValueError("BACKUP_COPY_FILE_MISSING_OR_OVERSIZED")
    data = path.read_bytes()
    if len(data) > maximum:
        raise ValueError("BACKUP_COPY_FILE_OVERSIZED")
    return data


def read_text(path: Path, maximum: int = 1024 * 1024) -> str:
    data = read_bytes(path, maximum).decode("utf-8")
    if "\x00" in data or "\r" in data.replace("\r\n", ""):
        raise ValueError("BACKUP_COPY_TEXT_INVALID")
    return data.replace("\r\n", "\n")


def digest_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_APK_BYTES:
        raise ValueError("BACKUP_COPY_APK_FILE_INVALID")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(block)
            if total > MAX_APK_BYTES:
                raise ValueError("BACKUP_COPY_APK_FILE_OVERSIZED")
            digest.update(block)
    return digest.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("BACKUP_COPY_METADATA_DUPLICATE_KEY")
        result[key] = value
    return result


def checksum(path: Path, expected_name: str) -> str:
    match = re.fullmatch(r"([0-9a-f]{64})[ \t]+\*?" + re.escape(expected_name) + r"\n?",
                         read_text(path, 4096))
    if not match:
        raise ValueError("BACKUP_COPY_CHECKSUM_MANIFEST_INVALID")
    return match.group(1)


def verify_badging(data: str, package: str, *, debug: bool = False) -> None:
    packages = re.findall(r"(?m)^package: name='([^']+)'(?: [^\n]*)?$", data)
    if packages != [package] or not data.startswith("package: name='"):
        raise ValueError("BACKUP_COPY_ACTUAL_PACKAGE_MISMATCH")
    if debug and len(re.findall(r"(?m)^application-debuggable$", data)) != 1:
        raise ValueError("BACKUP_COPY_ACTUAL_APK_NOT_DEBUGGABLE")


def verify_signature(data: str, expected: str) -> None:
    certs = re.findall(r"(?m)^Signer #([1-9][0-9]*) certificate SHA-256 digest: ([0-9a-f]{64})$", data)
    signer_ids = set(re.findall(r"(?m)^Signer #([1-9][0-9]*) ", data))
    if (certs != [("1", expected)] or signer_ids != {"1"}
            or len(re.findall(r"(?m)^Verifies$", data)) != 1
            or re.findall(r"(?m)^Number of signers: ([0-9]+)$", data) != ["1"]
            or not re.search(r"(?m)^Verified using v[1-4](?:\.1)? scheme[^\n]*: true$", data)
            or re.search(r"DOES NOT VERIFY|(?m:^ERROR:)", data)):
        raise ValueError("BACKUP_COPY_APK_SIGNATURE_INVALID")


def verify_phase(data: str, phase: str, archive_sha256: str) -> dict:
    if phase not in PHASE_FLAGS:
        raise ValueError("BACKUP_COPY_PHASE_INVALID")
    if re.search(r"FAILURES!!!|INSTRUMENTATION_FAILED|INSTRUMENTATION_ABORTED|shortMsg=", data):
        raise ValueError("BACKUP_COPY_INSTRUMENTATION_FAILED")
    statuses = []
    current = {}
    custom = {}
    success_lines = []
    terminal = []
    last_status = -1
    lines = data.splitlines()
    for index, line in enumerate(lines):
        status = re.fullmatch(r"INSTRUMENTATION_STATUS: ([A-Za-z0-9_]+)=(.*)", line)
        code = re.fullmatch(r"INSTRUMENTATION_STATUS_CODE: (-?[0-9]+)", line)
        result = re.fullmatch(r"INSTRUMENTATION_RESULT: ([A-Za-z0-9_]+)=(.*)", line)
        final = re.fullmatch(r"INSTRUMENTATION_CODE: (-?[0-9]+)", line)
        ok = re.fullmatch(r"[ \t]*OK \(([0-9]+) tests?\)[ \t]*", line)
        if status:
            key, value = status.groups()
            if key in current:
                raise ValueError("BACKUP_COPY_DUPLICATE_TEST_FIELD")
            if key in {"stack", "shortMsg"} or (key in {"numtests", "current"} and value != "1"):
                raise ValueError("BACKUP_COPY_INSTRUMENTATION_TEST_INVALID")
            current[key] = value
        elif code:
            identity = (current.get("class"), current.get("test"))
            if identity != (TEST_CLASS, TEST_METHOD):
                raise ValueError("BACKUP_COPY_INSTRUMENTATION_TEST_ID_INVALID")
            statuses.append((identity, int(code.group(1))))
            current = {}
            last_status = index
        elif result:
            key, value = result.groups()
            if key.startswith("kral_backup_"):
                if key in custom:
                    raise ValueError("BACKUP_COPY_DUPLICATE_RESULT_KEY")
                custom[key] = value
        elif final:
            terminal.append((index, final.group(1)))
        elif ok:
            success_lines.append((index, ok.group(1)))
        elif line.startswith(("INSTRUMENTATION_STATUS", "INSTRUMENTATION_RESULT", "INSTRUMENTATION_CODE")):
            raise ValueError("BACKUP_COPY_INSTRUMENTATION_LINE_INVALID")
        elif line.lstrip().startswith("OK"):
            raise ValueError("BACKUP_COPY_INSTRUMENTATION_SUMMARY_INVALID")
    expected_statuses = [((TEST_CLASS, TEST_METHOD), 1), ((TEST_CLASS, TEST_METHOD), 0)]
    if current or statuses != expected_statuses:
        raise ValueError("BACKUP_COPY_INSTRUMENTATION_TEST_SEQUENCE_INVALID")
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    if (len(terminal) != 1 or terminal[0] != (nonempty[-1], "-1")
            or len(success_lines) != 1 or success_lines[0][1] != "1"
            or not last_status < success_lines[0][0] < terminal[0][0]):
        raise ValueError("BACKUP_COPY_INSTRUMENTATION_SUCCESS_MISSING")
    flags = COMMON_FLAGS | PHASE_FLAGS[phase]
    expected_keys = flags | {"kral_backup_phase", "kral_backup_archive_sha256"}
    if (set(custom) != expected_keys or custom.get("kral_backup_phase") != phase
            or custom.get("kral_backup_archive_sha256") != archive_sha256
            or any(custom.get(flag) != "true" for flag in flags)):
        raise ValueError("BACKUP_COPY_NATIVE_RESULT_INVALID")
    return {"phase": phase, "test_class": TEST_CLASS, "test_method": TEST_METHOD,
            "instrumentation_tests": 1, "instrumentation_passed": True,
            "archive_sha256": archive_sha256, "native_flags": sorted(flags)}


def preflight(evidence_dir: Path, apk_dir: Path, env=None) -> dict:
    """Validate build identities and tool evidence before installing any package."""
    env = os.environ if env is None else env
    source_sha = env.get("KRAL_EXPECTED_SOURCE_SHA", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    if (not SOURCE.fullmatch(source_sha) or env.get("KRAL_EMULATOR_API") != "30"
            or not re.fullmatch(r"[1-9][0-9]*", run_id)):
        raise ValueError("BACKUP_COPY_EXECUTION_IDENTITY_INVALID")
    metadata = json.loads(read_text(apk_dir / "apk-metadata.json", 128 * 1024),
                          object_pairs_hook=unique_object)
    if (not isinstance(metadata, dict) or metadata.get("source_commit") != source_sha
            or metadata.get("expected_source_commit") != source_sha
            or metadata.get("github_run_id") != run_id or metadata.get("package") != PACKAGE
            or metadata.get("apk") != "app-debug.apk"
            or any(metadata.get(key) is not True for key in (
                "exact_source_head_verified", "source_tree_clean", "signature_verified", "debuggable", "standalone_apk"))):
        raise ValueError("BACKUP_COPY_BUILD_IDENTITY_MISMATCH")
    certs = metadata.get("signer_certificate_sha256")
    if not isinstance(certs, list) or len(certs) != 1 or not isinstance(certs[0], str) or not HASH.fullmatch(certs[0]):
        raise ValueError("BACKUP_COPY_BUILD_SIGNER_INVALID")
    apk = apk_dir / "app-debug.apk"
    test_apk = apk_dir / "app-debug-androidTest.apk"
    apk_sha256, test_sha256 = digest_file(apk), digest_file(test_apk)
    if (metadata.get("sha256") != apk_sha256
            or type(metadata.get("size_bytes")) is not int or metadata["size_bytes"] != apk.stat().st_size
            or checksum(apk_dir / "APK-SHA256SUMS", apk.name) != apk_sha256
            or checksum(apk_dir / "TEST-APK-SHA256SUMS", test_apk.name) != test_sha256):
        raise ValueError("BACKUP_COPY_APK_HASH_MISMATCH")
    verify_badging(read_text(evidence_dir / "app-badging.txt", 128 * 1024), PACKAGE, debug=True)
    verify_badging(read_text(evidence_dir / "test-badging.txt", 128 * 1024), TEST_PACKAGE)
    verify_signature(read_text(evidence_dir / "app-signature.txt", 128 * 1024), certs[0])
    verify_signature(read_text(evidence_dir / "test-signature.txt", 128 * 1024), certs[0])
    return {"validation_phase": "preflight", "source_commit": source_sha, "github_run_id": run_id,
            "package": PACKAGE, "test_package": TEST_PACKAGE, "apk_sha256": apk_sha256,
            "test_apk_sha256": test_sha256, "signer_certificate_sha256": certs[0],
            "physical_phone_tested": False, "second_device_identity_verified": False,
            "owner_authentication_tested": False}


def emulator_identity(evidence_dir: Path) -> str:
    for filename, expected in (("qemu.txt", "1"), ("api-level.txt", "30"), ("abi.txt", "x86_64")):
        if read_text(evidence_dir / filename, 1024).strip() != expected:
            raise ValueError("BACKUP_COPY_DISPOSABLE_EMULATOR_REQUIRED")
    serial = read_text(evidence_dir / "device-serial.txt", 1024).strip()
    if not re.fullmatch(r"emulator-[0-9]+", serial):
        raise ValueError("BACKUP_COPY_DISPOSABLE_EMULATOR_REQUIRED")
    return serial


def empty_packages(evidence_dir: Path, names) -> None:
    for name in names:
        if read_text(evidence_dir / name, 4096).strip():
            raise ValueError("BACKUP_COPY_PREEXISTING_PACKAGE")


def successful_package_operations(evidence_dir: Path, names) -> None:
    for name in names:
        data = read_text(evidence_dir / (name + ".txt"), 64 * 1024)
        if len(re.findall(r"(?m)^Success[ \t]*$", data)) != 1 or re.search(r"failure|failed|error", data, re.I):
            raise ValueError("BACKUP_COPY_INSTALL_OR_UNINSTALL_FAILED")


def archive_identity(evidence_dir: Path) -> tuple[str, int]:
    archive = read_bytes(evidence_dir / "kral-installation-backup.bin", MAX_BACKUP_BYTES)
    if (len(archive) < 80 or archive[:8] != b"KRALBAK1"
            or struct.unpack(">III", archive[8:20]) != (1, 3, 310_000)
            or struct.unpack(">I", archive[48:52])[0] != len(archive) - 52):
        raise ValueError("BACKUP_COPY_ARCHIVE_FORMAT_INVALID")
    archive_sha256 = hashlib.sha256(archive).hexdigest()
    return archive_sha256, len(archive)


def verify_export(evidence_dir: Path, apk_dir: Path, env=None) -> dict:
    """Validate the exported archive before uninstalling the fixture packages."""
    result = preflight(evidence_dir, apk_dir, env)
    serial = emulator_identity(evidence_dir)
    empty_packages(evidence_dir, ("app-before.txt", "test-before.txt"))
    successful_package_operations(evidence_dir, ("source-install-app", "source-install-test"))
    archive_sha256, archive_size = archive_identity(evidence_dir)
    phase = verify_phase(read_text(evidence_dir / "export-result.txt"), "export", archive_sha256)
    result.update(validation_phase="export", backup_archive_sha256=archive_sha256,
                  backup_archive_size_bytes=archive_size, source_installation_fresh=True,
                  source_keystore_key_created=True, source_rows_verified=True,
                  encrypted_archive_verified=True, encrypted_database_verified=True,
                  device_serial=serial, api_level=30, abi="x86_64", phase_results=[phase])
    return result


def verify(evidence_dir: Path, apk_dir: Path, env=None) -> dict:
    result = verify_export(evidence_dir, apk_dir, env)
    empty_packages(evidence_dir, ("app-between.txt", "test-between.txt"))
    successful_package_operations(evidence_dir, ("source-uninstall-app", "source-uninstall-test",
                                                "target-install-app", "target-install-test"))
    phase = verify_phase(read_text(evidence_dir / "restore-result.txt"), "restore",
                         result["backup_archive_sha256"])
    result["phase_results"].append(phase)
    result.update({"validation_phase": "complete", "same_archive_verified_in_both_phases": True,
            "target_installation_fresh": True,
            "target_keystore_key_created": True, "encrypted_archive_verified": True,
            "encrypted_database_verified": True, "restore_verified": True, "reopen_verified": True,
            "fresh_installation_copy_verified": True, "same_emulator_reinstallation": True,
            "physical_phone_tested": False, "second_device_identity_verified": False,
            "owner_authentication_tested": False})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("apk_dir", type=Path)
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument("--preflight", action="store_true", help="Validate APKs only, before installing")
    phase.add_argument("--export-only", action="store_true", help="Validate export, before fixture uninstall")
    args = parser.parse_args()
    if args.preflight or args.export_only:
        operation = preflight if args.preflight else verify_export
        print(json.dumps(operation(args.evidence_dir, args.apk_dir)))
        return
    output = args.evidence_dir / "backup-copy-result.json"
    if output.is_symlink() or output.is_dir():
        raise ValueError("BACKUP_COPY_RESULT_PATH_INVALID")
    output.unlink(missing_ok=True)
    result = verify(args.evidence_dir, args.apk_dir)
    temporary = output.with_name("." + output.name + f".{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
