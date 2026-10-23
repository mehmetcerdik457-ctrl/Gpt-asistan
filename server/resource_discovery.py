"""Bounded, read-only KRAL source inventory. Never execute or unpack inputs.

This only verifies file bytes and format *hints*. It does not prove a model,
APK, API connection, license, ownership, or capability works.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

IGNORED_DIRECTORIES = frozenset({
    ".git", ".gradle", ".idea", ".ssh", ".venv", "__pycache__",
    "node_modules", "secrets", "keyrings",
})
SECRET_FILE_NAMES = frozenset({
    ".env", "id_rsa", "id_ed25519", "credentials.json",
    "service-account.json", "google-services.json",
})
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".jks", ".keystore", ".p8")
TYPE_HINTS = {
    ".apk": "android_apk", ".aab": "android_bundle",
    ".apks": "android_split_set", ".gguf": "model_gguf",
    ".onnx": "model_onnx", ".safetensors": "model_weights",
    ".zip": "archive_zip", ".tar": "archive_tar",
    ".gz": "compressed_file", ".jar": "java_library",
    ".aar": "android_library", ".so": "native_library",
    ".kt": "kotlin_source", ".java": "java_source",
    ".py": "python_source", ".js": "javascript_source",
    ".json": "json_document", ".md": "markdown_document",
}


def _secret_name(name: str) -> bool:
    lowered = name.lower()
    return (lowered in SECRET_FILE_NAMES
            or lowered.startswith(".env.")
            or lowered.endswith(SECRET_SUFFIXES))


def _digest_regular_file(path: Path, before: os.stat_result) -> str:
    """No symlink following; reject a changed path or file modified mid-read."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if not hasattr(os, "O_NOFOLLOW"):
        raise OSError("O_NOFOLLOW unavailable; refusing unsafe scan")
    descriptor = os.open(path, flags | os.O_NOFOLLOW)
    try:
        observed = os.fstat(descriptor)
        if (not stat.S_ISREG(observed.st_mode)
                or (observed.st_dev, observed.st_ino, observed.st_size,
                    observed.st_mtime_ns) !=
                   (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns)):
            raise OSError("file changed before scan")
        digest = hashlib.sha256()
        count = 0
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > before.st_size:
                    raise OSError("file grew during scan")
                digest.update(chunk)
        after = os.fstat(descriptor)
        if (count != before.st_size or
                (after.st_size, after.st_mtime_ns) !=
                (before.st_size, before.st_mtime_ns)):
            raise OSError("file changed during scan")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def discover(root: str | Path, *, max_files: int = 500,
             max_file_bytes: int = 128 * 1024 * 1024,
             max_total_bytes: int = 512 * 1024 * 1024) -> dict:
    """Inspect explicitly provided local root, no mutation and no execution.

    Positive limits bound reads; unsafe/sensitive/oversized files are BLOCKED.
    A hashed file is VERIFIED_FILE only, never TESTED or CONNECTED.
    """
    if min(max_files, max_file_bytes, max_total_bytes) <= 0:
        raise ValueError("All scan limits must be positive")
    root = Path(root)
    if root.is_symlink():
        raise ValueError("Symlink root is not allowed")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Source root must be a directory")

    records: list[dict] = []
    seen_hashes: dict[str, str] = {}
    bytes_read = 0
    ignored_directories = 0
    truncated = False
    for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
        safe_dirs = []
        for dirname in sorted(dirs):
            item = Path(current) / dirname
            if dirname.lower() in IGNORED_DIRECTORIES or item.is_symlink():
                ignored_directories += 1
            else:
                safe_dirs.append(dirname)
        dirs[:] = safe_dirs

        for name in sorted(names):
            if len(records) >= max_files:
                truncated = True
                break
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            record = {
                "source_id": relative,
                "format_hint": TYPE_HINTS.get(path.suffix.lower(), "unknown"),
                "status": "BLOCKED",
                "capability_status": "UNTESTED",
                "integration_status": "NOT_CONNECTED",
            }
            records.append(record)
            if _secret_name(name):
                record["reason"] = "SENSITIVE_NAME"
                continue
            try:
                before = path.lstat()
                if not stat.S_ISREG(before.st_mode):
                    record["reason"] = "NOT_REGULAR_FILE_OR_SYMLINK"
                    continue
                record["size_bytes"] = before.st_size
                if before.st_size > max_file_bytes:
                    record["reason"] = "FILE_LIMIT_EXCEEDED"
                    continue
                if bytes_read + before.st_size > max_total_bytes:
                    record["reason"] = "TOTAL_LIMIT_EXCEEDED"
                    continue
                digest = _digest_regular_file(path, before)
            except (OSError, ValueError) as error:
                record["reason"] = type(error).__name__ + ":READ_FAILED"
                continue
            bytes_read += before.st_size
            record.update(status="VERIFIED_FILE", sha256=digest)
            if digest in seen_hashes:
                record["duplicate_of"] = seen_hashes[digest]
            else:
                seen_hashes[digest] = relative
        if truncated:
            break

    return {
        "schema": "kral.source_manifest.v1",
        "root": str(root),
        "read_only": True,
        "scan_truncated": truncated,
        "ignored_directories": ignored_directories,
        "bytes_hashed": bytes_read,
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Explicit local source directory to inspect")
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--max-file-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=512 * 1024 * 1024)
    args = parser.parse_args()
    manifest = discover(args.root, max_files=args.max_files,
                        max_file_bytes=args.max_file_bytes,
                        max_total_bytes=args.max_total_bytes)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
