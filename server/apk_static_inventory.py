"""Static, bounded APK ZIP-structure evidence (no extraction or execution).

A ZIP member list is NOT a signature, package-ID, install, model, or ABI
compatibility verification. Signed identity requires Android SDK apksigner.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

ABI = frozenset({"armeabi-v7a", "arm64-v8a", "x86", "x86_64"})
DEX = re.compile(r"classes(?:[2-9][0-9]*)?\.dex\Z")


class ApkUnsafe(Exception):
    """A static inspection safety boundary rejected the input."""


def inspect_apk(path, *, expected_sha256,
                max_entries=10000, max_total_uncompressed=512 * 1024 * 1024,
                max_single_uncompressed=256 * 1024 * 1024):
    """Inspect an already hashed file through a no-follow, read-only fd.

    Strict limits cover ZIP metadata claims; no members are decompressed.
    Refuse changed source bytes and misleading path traversal members.
    """
    if not isinstance(expected_sha256, str) or re.fullmatch(
        r"[a-f0-9]{64}", expected_sha256
    ) is None:
        raise ValueError("Expected SHA-256 required")
    if min(max_entries, max_total_uncompressed, max_single_uncompressed) <= 0:
        raise ValueError("Inspection limits must be positive")
    if not hasattr(os, "O_NOFOLLOW"):
        return {"status": "BLOCKED", "reason": "NO_NOFOLLOW"}
    path = Path(path)
    if path.is_symlink():
        return {"status": "BLOCKED", "reason": "SOURCE_SYMLINK"}
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            return {"status": "BLOCKED", "reason": "NOT_REGULAR"}
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW |
                     getattr(os, "O_CLOEXEC", 0))
        with os.fdopen(fd, "rb") as stream:
            start = os.fstat(stream.fileno())
            if not stat.S_ISREG(start.st_mode) or (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
            ) != (start.st_dev, start.st_ino, start.st_size, start.st_mtime_ns):
                raise ApkUnsafe("SOURCE_CHANGED")
            digest = hashlib.sha256()
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            if digest.hexdigest() != expected_sha256:
                raise ApkUnsafe("SOURCE_HASH_CHANGED")
            stream.seek(0)
            with zipfile.ZipFile(stream, "r") as apk:
                infos = apk.infolist()
                if len(infos) > max_entries:
                    raise ApkUnsafe("ZIP_ENTRY_LIMIT")
                names = set()
                dex = set()
                arch = set()
                so_count = 0
                total = 0
                has_manifest = False
                for info in infos:
                    name = info.filename
                    pure = PurePosixPath(name)
                    if (not name or name.startswith("/") or "\\" in name or
                        any(part in ("..", ".") for part in name.split("/")) or
                        pure.is_absolute()):
                        raise ApkUnsafe("ZIP_UNSAFE_ENTRY")
                    if name in names:
                        raise ApkUnsafe("ZIP_DUPLICATE_ENTRY")
                    names.add(name)
                    if info.flag_bits & 1:
                        raise ApkUnsafe("ZIP_ENCRYPTED_ENTRY")
                    if info.file_size > max_single_uncompressed:
                        raise ApkUnsafe("ZIP_MEMBER_LIMIT")
                    total += info.file_size
                    if total > max_total_uncompressed:
                        raise ApkUnsafe("ZIP_TOTAL_LIMIT")
                    has_manifest |= name == "AndroidManifest.xml"
                    if DEX.fullmatch(name):
                        dex.add(name)
                    match = re.fullmatch(r"lib/([^/]+)/([^/]+\.so)", name)
                    if match:
                        so_count += 1
                        if match.group(1) in ABI:
                            arch.add(match.group(1))
            end = os.fstat(stream.fileno())
            if (start.st_size, start.st_mtime_ns) != (
                end.st_size, end.st_mtime_ns
            ):
                raise ApkUnsafe("SOURCE_CHANGED")
        if not has_manifest:
            return {"status": "INVALID_APK_STRUCTURE",
                    "reason": "ANDROID_MANIFEST_MISSING"}
        return {"status": "ZIP_STRUCTURE_VERIFIED",
                "manifest_present": True,
                "dex_count": len(dex),
                "native_library_count": so_count,
                "native_abis": sorted(arch),
                "zip_entries": len(infos),
                "uncompressed_size_claimed": total,
                "signature_verified": False,
                "install_tested": False,
                "model_inference_tested": False}
    except (ApkUnsafe, OSError, zipfile.BadZipFile,
            zipfile.LargeZipFile, EOFError, RuntimeError) as exc:
        return {"status": "BLOCKED",
                "reason": str(exc) if isinstance(exc, ApkUnsafe)
                else type(exc).__name__}
