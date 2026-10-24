"""Owner-gated, read-only inspection using no-follow, anchored file descriptors.

Use only a trusted absolute KRAL_SOURCE_ROOT with a read-only source mount.
A source is never executed, extracted or implicitly added as a capability.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

from .resource_discovery import (_secret_name, IGNORED_DIRECTORIES, TYPE_HINTS)
from .apk_static_inventory import inspect_apk


class SourceInspectionDenied(Exception):
    """Fixed, non-sensitive failure codes only."""


def _open_beneath(root_path: Path, components: list[str]):
    """Pin every ancestor with a dirfd to prevent intermediate symlink swaps."""
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise SourceInspectionDenied("SOURCE_PLATFORM_UNSUPPORTED")
    common_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    folder_flags = common_flags | os.O_DIRECTORY
    handles = []
    try:
        parent = os.open(root_path, folder_flags)
        handles.append(parent)
        for component in components[:-1]:
            # lstat-like preflight is only for a stable error code; the
            # O_NOFOLLOW+dirfd open below remains the security boundary.
            if stat.S_ISLNK(os.stat(component, dir_fd=parent, follow_symlinks=False).st_mode):
                raise SourceInspectionDenied("SOURCE_LINK_DENIED")
            parent = os.open(component, folder_flags, dir_fd=parent)
            handles.append(parent)
        if stat.S_ISLNK(os.stat(components[-1], dir_fd=parent, follow_symlinks=False).st_mode):
            raise SourceInspectionDenied("SOURCE_LINK_DENIED")
        # O_NONBLOCK avoids blocking on a substituted FIFO.
        file_fd = os.open(components[-1],
                          common_flags | getattr(os, "O_NONBLOCK", 0),
                          dir_fd=parent)
        handles.append(file_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise SourceInspectionDenied("SOURCE_FILE_DENIED")
        handles.pop()
        return os.fdopen(file_fd, "rb", closefd=True)
    finally:
        for fd in reversed(handles):
            os.close(fd)


def inspect_source(root: str, source_id: str, *,
                   max_file_bytes: int = 128 * 1024 * 1024) -> dict:
    """Hash one allowlisted file; inspect APK ZIP metadata through same descriptor."""
    if not isinstance(root, str) or not root.strip():
        raise SourceInspectionDenied("SOURCE_ROOT_NOT_CONFIGURED")
    if (not isinstance(source_id, str) or not 0 < len(source_id) <= 512
        or source_id.startswith("/") or "\\" in source_id
        or any(ord(c) < 32 for c in source_id)):
        raise SourceInspectionDenied("SOURCE_ID_INVALID")
    if type(max_file_bytes) is not int or max_file_bytes <= 0:
        raise SourceInspectionDenied("SOURCE_SCAN_LIMIT_INVALID")
    components = source_id.split("/")
    if (any(c in ("", ".", "..") for c in components)
        or any(_secret_name(c) or c.lower() in IGNORED_DIRECTORIES or
               c.startswith(".") for c in components)):
        raise SourceInspectionDenied("SOURCE_PATH_DENIED")
    suffix = Path(components[-1]).suffix.lower()
    if suffix not in TYPE_HINTS:
        raise SourceInspectionDenied("SOURCE_TYPE_NOT_ALLOWED")
    root_path = Path(root)
    if (not root_path.is_absolute() or root_path.is_symlink()
        or not root_path.is_dir()):
        raise SourceInspectionDenied("SOURCE_ROOT_INVALID")
    try:
        with _open_beneath(root_path, components) as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > max_file_bytes:
                raise SourceInspectionDenied("SOURCE_SIZE_LIMIT")
            digest = hashlib.sha256()
            count = 0
            while True:
                chunk = stream.read(min(1024 * 1024, max_file_bytes - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                if count > max_file_bytes or count > before.st_size:
                    raise SourceInspectionDenied("SOURCE_SIZE_LIMIT")
                digest.update(chunk)
            after = os.fstat(stream.fileno())
            if (count != before.st_size or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise SourceInspectionDenied("SOURCE_CHANGED")
            hash_value = digest.hexdigest()
            structure = (inspect_apk(None, expected_sha256=hash_value,
                                     source_fd=stream.fileno()) if suffix == ".apk" else None)
    except FileNotFoundError:
        raise SourceInspectionDenied("SOURCE_NOT_FOUND") from None
    except PermissionError:
        raise SourceInspectionDenied("SOURCE_ACCESS_DENIED") from None
    except OSError:
        raise SourceInspectionDenied("SOURCE_READ_DENIED") from None
    evidence = {
        "source_id": source_id,
        "size_bytes": before.st_size,
        "sha256": hash_value,
        "format_hint": TYPE_HINTS[suffix],
        "status": "VERIFIED_FILE",
        "capability_status": "UNTESTED",
        "integration_status": "NOT_CONNECTED",
        "read_only": True,
    }
    if structure is not None:
        evidence["apk_structure"] = structure
        if structure["status"] == "ZIP_STRUCTURE_VERIFIED":
            evidence["status"] = "ANALYZED_STATIC"
    return evidence
