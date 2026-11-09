"""Fail-closed, read-only source intake for KRAL's 13-stage acquisition flow.

This function deliberately performs ONLY static identity and bounded archive
inspection. Never runs APK/SDK/model code, extracts files, follows symlinks,
uses credentials, or registers a live capability. Not an APK signer verifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile

MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10000
MAX_TOTAL_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
HASH_CHUNK = 1024 * 1024


class IntakeRejected(ValueError):
    """Untrusted source cannot be safely classified."""


def _hash_stream(file) -> str:
    digest = hashlib.sha256()
    file.seek(0)
    while True:
        block = file.read(HASH_CHUNK)
        if not block:
            break
        digest.update(block)
    return digest.hexdigest()


def _scan_archive(file) -> dict:
    file.seek(0)
    try:
        with zipfile.ZipFile(file, "r", allowZip64=True) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise IntakeRejected("ARCHIVE_ENTRY_LIMIT")
            seen = set()
            total_size = 0
            paths = set()
            for item in infos:
                name = item.filename
                # Never trust archive paths even though no extraction occurs.
                if (not name or "\x00" in name or "\\" in name or
                        name.startswith("/") or
                        ":" in name.split("/", 1)[0] or
                        any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))):
                    raise IntakeRejected("ARCHIVE_UNSAFE_PATH")
                canonical = str(PurePosixPath(name.rstrip("/")))
                if canonical in seen:
                    raise IntakeRejected("ARCHIVE_DUPLICATE_PATH")
                seen.add(canonical)
                if item.flag_bits & 1:
                    raise IntakeRejected("ARCHIVE_ENCRYPTED_ENTRY")
                mode = (item.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise IntakeRejected("ARCHIVE_SPECIAL_ENTRY")
                if item.file_size < 0 or item.compress_size < 0:
                    raise IntakeRejected("ARCHIVE_INVALID_SIZE")
                if not item.is_dir():
                    total_size += item.file_size
                    if total_size > MAX_TOTAL_UNCOMPRESSED:
                        raise IntakeRejected("ARCHIVE_UNCOMPRESSED_SIZE_LIMIT")
                    if item.file_size > MAX_COMPRESSION_RATIO * max(1, item.compress_size):
                        raise IntakeRejected("ARCHIVE_COMPRESSION_BOMB")
                paths.add(canonical)
            is_apk = "AndroidManifest.xml" in paths and any(
                item == "classes.dex" or
                (item.startswith("classes") and item.endswith(".dex"))
                for item in paths
            )
            is_aab = ("BundleConfig.pb" in paths and
                      "base/manifest/AndroidManifest.xml" in paths)
            archive_type = "apk_candidate" if is_apk else "aab_candidate" if is_aab else "zip_archive"
            abis = sorted({
                bits[1] for path in paths
                for bits in [path.split("/")]
                if len(bits) == 3 and bits[0] == "lib" and bits[2].endswith(".so")
            })
            return {
                "format": archive_type,
                "archive_entries": len(infos),
                "archive_total_uncompressed_bytes": total_size,
                "abi_paths_observed": abis,
                "android_manifest_path_observed": is_apk or is_aab,
                "dex_path_observed": any(p.endswith(".dex") for p in paths),
                "signature_certificate_verified": False,
                "package_name_verified": False,
            }
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError):
        raise IntakeRejected("ARCHIVE_INVALID") from None


def inspect_file(path: str | os.PathLike[str]) -> dict:
    """Inspect one regular local file without changing the original."""
    filename = os.fspath(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(filename, flags)
    except OSError:
        raise IntakeRejected("SOURCE_UNREADABLE_OR_SYMLINK") from None
    with os.fdopen(fd, "rb", closefd=True) as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise IntakeRejected("SOURCE_NOT_REGULAR_FILE")
        if before.st_size < 1 or before.st_size > MAX_SOURCE_BYTES:
            raise IntakeRejected("SOURCE_SIZE_OUT_OF_BOUNDS")
        first_digest = _hash_stream(file)
        file.seek(0)
        header = file.read(8)
        if header[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
            details = _scan_archive(file)
        elif header.startswith(b"GGUF"):
            details = {"format": "gguf_header_candidate", "runtime_verified": False,
                       "model_weights_validated": False}
        elif header.startswith(b"\x7fELF"):
            details = {"format": "elf_binary", "executable_validated": False}
        elif header.startswith(b"%PDF-"):
            details = {"format": "pdf_document", "contents_validated": False}
        else:
            details = {"format": "unknown_binary", "format_verified": False}
        second_digest = _hash_stream(file)
        after = os.fstat(file.fileno())
        if (first_digest != second_digest or before.st_dev != after.st_dev or
                before.st_ino != after.st_ino or
                before.st_size != after.st_size or
                before.st_mtime_ns != after.st_mtime_ns or
                before.st_ctime_ns != after.st_ctime_ns):
            raise IntakeRejected("SOURCE_CHANGED_DURING_INSPECTION")
        return {
            "source_id": "sha256:" + first_digest,
            "name": Path(filename).name,
            "size_bytes": before.st_size,
            "sha256": first_digest,
            "source_status": "ANALYZED_STATIC_ONLY",
            "original_unchanged_during_read": True,
            "registered_as_capability": False,
            "external_api_called": False,
            "file_executed": False,
            "file_extracted": False,
            "real_device_tested": False,
            "limitations": [
                "Not a cryptographic APK signature or package verification",
                "Does not prove a running legacy bot, license, API permission, or usable model",
                "No connection or runtime capability granted",
            ],
            **details,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Explicitly selected files; no recursive scanning")
    arguments = parser.parse_args()
    if len(arguments.paths) > 1000:
        parser.error("At most 1000 explicit files per invocation")
    results = []
    had_errors = False
    for path in arguments.paths:
        try:
            results.append(inspect_file(path))
        except IntakeRejected as exc:
            # Do not publish absolute local paths or untrusted file contents.
            had_errors = True
            results.append({
                "name": Path(path).name,
                "source_status": "BLOCKED",
                "error_code": str(exc),
                "registered_as_capability": False,
            })
    print(json.dumps({"schema_version": 1, "inspection_mode": "READ_ONLY_STATIC",
                      "source_count": len(results),
                      "live_capabilities_registered": 0, "results": results},
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if had_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
