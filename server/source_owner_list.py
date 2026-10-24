"""Bounded Owner-only source ID discovery within a dedicated read-only mount.

The result is a *candidate file list*, not content verification or capability
activation. No file bytes are read and no source is ever executed or extracted.
Call this only after dual-P256 Owner authorization in gateway.py.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat

from .resource_discovery import IGNORED_DIRECTORIES, TYPE_HINTS, _secret_name
from .source_owner_tool import SourceInspectionDenied


def list_sources(root: str, *, max_files: int = 50,
                 max_entries: int = 500, max_depth: int = 3,
                 max_file_bytes: int = 128 * 1024 * 1024) -> dict:
    """Enumerate only safe relative source IDs, anchored by directory fds.

    Stop at strict resource limits, reject symlinks at every directory open,
    exclude hidden/credential-like components, and never hash or open content.
    """
    if not isinstance(root, str) or not root.strip():
        raise SourceInspectionDenied("SOURCE_ROOT_NOT_CONFIGURED")
    if (any(type(x) is not int for x in
            (max_files, max_entries, max_depth, max_file_bytes)) or
        not 1 <= max_files <= 50 or not 1 <= max_entries <= 500 or
        not 1 <= max_depth <= 3 or not 1 <= max_file_bytes <= 128 * 1024 * 1024):
        raise SourceInspectionDenied("SOURCE_LIST_LIMIT_INVALID")
    folder = Path(root)
    if not folder.is_absolute() or folder.is_symlink() or not folder.is_dir():
        raise SourceInspectionDenied("SOURCE_ROOT_INVALID")
    if not all(hasattr(os, key) for key in ("O_NOFOLLOW", "O_DIRECTORY")):
        raise SourceInspectionDenied("SOURCE_PLATFORM_UNSUPPORTED")
    dir_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
    results: list[dict] = []
    scanned = 0
    truncated = False

    def safe_name(name: str) -> bool:
        return (
            bool(name) and name not in (".", "..") and not name.startswith(".")
            and len(name) <= 255 and not any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
            and not _secret_name(name)
            and name.lower() not in IGNORED_DIRECTORIES
        )

    def visit(directory: int, prefix: str, depth: int) -> None:
        nonlocal scanned, truncated
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if scanned >= max_entries or len(results) >= max_files:
                        truncated = True
                        break
                    scanned += 1
                    name = entry.name
                    if not safe_name(name):
                        continue
                    identifier = prefix + name
                    if len(identifier) > 512:
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth >= max_depth:
                                continue
                            # Pin the child inode. A race replacing it with a
                            # symlink must fail rather than follow the target.
                            child_fd = os.open(name, dir_flags, dir_fd=directory)
                            try:
                                visit(child_fd, identifier + "/", depth + 1)
                            finally:
                                os.close(child_fd)
                        elif entry.is_file(follow_symlinks=False):
                            suffix = Path(name).suffix.lower()
                            if suffix not in TYPE_HINTS:
                                continue
                            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                            if stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= max_file_bytes:
                                results.append({
                                    "source_id": identifier,
                                    "format_hint": TYPE_HINTS[suffix],
                                    "size_bytes": info.st_size,
                                })
                    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
                        # A race or unreadable entry is not evidence and may
                        # never expand traversal outside the pinned root.
                        continue
        except OSError:
            # Treat unreadable or changing subdirectories as ignored. The
            # explicitly configured root is checked separately below.
            pass

    try:
        root_fd = os.open(folder, dir_flags)
    except OSError:
        raise SourceInspectionDenied("SOURCE_ROOT_ACCESS_DENIED") from None
    try:
        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            raise SourceInspectionDenied("SOURCE_ROOT_INVALID")
        visit(root_fd, "", 0)
    finally:
        os.close(root_fd)
    return {
        "sources": sorted(results, key=lambda r: r["source_id"]),
        "truncated": truncated,
        "read_only": True,
        "capability_status": "UNTESTED",
        "integration_status": "NOT_CONNECTED",
    }
