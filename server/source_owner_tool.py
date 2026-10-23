"""Owner-gated, read-only inspection of one explicitly allowlisted source.

Use only with a server-managed, read-only mount in KRAL_SOURCE_ROOT.
Never allow a model/remote document to choose a root or run source code.
"""
from __future__ import annotations

from pathlib import Path
import os
import stat

from .resource_discovery import (_digest_regular_file, _secret_name,
                                 IGNORED_DIRECTORIES, TYPE_HINTS, inspect_apk)


class SourceInspectionDenied(Exception):
    """Fixed, non-sensitive failure codes only."""


def inspect_source(root: str, source_id: str, *,
                   max_file_bytes: int = 128 * 1024 * 1024) -> dict:
    """Hash one safe existing file; no code execution, extraction or mutation."""
    if not isinstance(root, str) or not root.strip():
        raise SourceInspectionDenied("SOURCE_ROOT_NOT_CONFIGURED")
    if (not isinstance(source_id, str) or not 0 < len(source_id) <= 512
        or source_id.startswith("/") or "\\" in source_id
        or any(ord(c) < 32 for c in source_id)):
        raise SourceInspectionDenied("SOURCE_ID_INVALID")
    if not isinstance(max_file_bytes, int) or max_file_bytes <= 0:
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

    # Reject existing symlinks in any user-selected component; do not follow.
    path = root_path
    try:
        for index, component in enumerate(components):
            path = path / component
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise SourceInspectionDenied("SOURCE_LINK_DENIED")
            if index < len(components) - 1:
                if not stat.S_ISDIR(info.st_mode):
                    raise SourceInspectionDenied("SOURCE_PATH_DENIED")
            elif not stat.S_ISREG(info.st_mode):
                raise SourceInspectionDenied("SOURCE_FILE_DENIED")
        before = path.lstat()
        if before.st_size > max_file_bytes:
            raise SourceInspectionDenied("SOURCE_SIZE_LIMIT")
        digest = _digest_regular_file(path, before)
        after = path.lstat()
        if (before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns) != (after.st_dev, after.st_ino,
                                   after.st_size, after.st_mtime_ns):
            raise SourceInspectionDenied("SOURCE_CHANGED")
    except FileNotFoundError:
        raise SourceInspectionDenied("SOURCE_NOT_FOUND") from None
    except PermissionError:
        raise SourceInspectionDenied("SOURCE_ACCESS_DENIED") from None
    except OSError:
        raise SourceInspectionDenied("SOURCE_READ_DENIED") from None

    evidence = {
        "source_id": source_id,
        "size_bytes": before.st_size,
        "sha256": digest,
        "format_hint": TYPE_HINTS[suffix],
        "status": "VERIFIED_FILE",
        "capability_status": "UNTESTED",
        "integration_status": "NOT_CONNECTED",
        "read_only": True,
    }
    if suffix == ".apk":
        structure = inspect_apk(path, expected_sha256=digest)
        evidence["apk_structure"] = structure
        if structure["status"] == "ZIP_STRUCTURE_VERIFIED":
            evidence["status"] = "ANALYZED_STATIC"
    return evidence
