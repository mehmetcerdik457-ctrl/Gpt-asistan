"""Fail-closed creation and permission checks for private SQLite databases."""
import os
import stat
from pathlib import Path


def secure_sqlite_file(raw_path):
    """Return an absolute private DB path, rejecting symlinks and unsafe parents."""
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError("SQLite path must be absolute")

    parent = path.parent.stat()
    if not stat.S_ISDIR(parent.st_mode):
        raise ValueError("SQLite parent must be a directory")
    if parent.st_uid not in {os.geteuid(), 0} or parent.st_mode & 0o022:
        raise ValueError("SQLite parent must not be writable by group or others")

    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("SQLite path must be an owned regular file")
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    return str(path)
