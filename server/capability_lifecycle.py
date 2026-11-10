"""Local, disabled-by-default, source-digest-bound capability registry.

Only a deterministic text-line filter is implemented. Neither a source
package nor an AI model can grant itself execution or remote tool privileges.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys

from .source_intake import inspect_file, IntakeRejected

ID = re.compile(r"[a-z][a-z0-9_.-]{2,47}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
FIELDS = {"version", "id", "operation", "needle", "case_sensitive", "limit"}


class Refused(ValueError):
    pass


def _read(path, max_size):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(os.fspath(path), flags)
    except OSError:
        raise Refused("FILE_MISSING_OR_SYMLINK") from None
    with os.fdopen(fd, "rb") as stream:
        start = os.fstat(stream.fileno())
        if not stat.S_ISREG(start.st_mode) or not 0 < start.st_size <= max_size:
            raise Refused("FILE_SIZE_OR_TYPE_DENIED")
        value = stream.read(max_size + 1)
        end = os.fstat(stream.fileno())
        if (len(value) != start.st_size or
                (start.st_dev, start.st_ino, start.st_size,
                 start.st_mtime_ns, start.st_ctime_ns) !=
                (end.st_dev, end.st_ino, end.st_size, end.st_mtime_ns, end.st_ctime_ns)):
            raise Refused("FILE_CHANGED_DURING_READ")
        return value


def _unique(items):
    data = {}
    for key, value in items:
        if key in data:
            raise Refused("DUPLICATE_RECIPE_KEY")
        data[key] = value
    return data


def _recipe(raw):
    try:
        obj = json.loads(raw, object_pairs_hook=_unique)
    except (UnicodeDecodeError, TypeError, json.JSONDecodeError):
        raise Refused("INVALID_RECIPE_JSON") from None
    if not isinstance(obj, dict) or set(obj) != FIELDS or obj["version"] != 1:
        raise Refused("INVALID_RECIPE_SCHEMA")
    if type(obj["version"]) is not int or not isinstance(obj["id"], str) or not ID.fullmatch(obj["id"]):
        raise Refused("INVALID_CAPABILITY_ID")
    if obj["operation"] != "text.filter_lines":
        raise Refused("OPERATION_NOT_ALLOWLISTED")
    if (not isinstance(obj["needle"], str) or not 1 <= len(obj["needle"]) <= 80
            or any(ord(x) < 32 for x in obj["needle"])):
        raise Refused("INVALID_RECIPE_NEEDLE")
    if type(obj["case_sensitive"]) is not bool or type(obj["limit"]) is not int or not 1 <= obj["limit"] <= 20:
        raise Refused("INVALID_RECIPE_LIMIT")
    return obj


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_absolute() or not self.path.parent.is_dir() or self.path.is_symlink():
            raise Refused("PRIVATE_DB_PATH_REQUIRED")
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS capability "
                       "(id TEXT PRIMARY KEY, source_sha TEXT NOT NULL, "
                       "recipe TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0)")
        os.chmod(self.path, 0o600)

    def _db(self):
        if self.path.is_symlink():
            raise Refused("PRIVATE_DB_PATH_REQUIRED")
        return sqlite3.connect(str(self.path), timeout=3)

    def register(self, path, approved_sha):
        if not isinstance(approved_sha, str) or not DIGEST.fullmatch(approved_sha):
            raise Refused("OWNER_SOURCE_SHA_REQUIRED")
        try:
            source = inspect_file(path)
        except IntakeRejected:
            raise Refused("SOURCE_STATIC_INSPECTION_FAILED") from None
        if source["sha256"] != approved_sha:
            raise Refused("SOURCE_DIGEST_MISMATCH")
        if source["format"] != "unknown_binary":
            raise Refused("SOURCE_NOT_DECLARATIVE_RECIPE")
        raw = _read(path, 16384)
        if hashlib.sha256(raw).hexdigest() != approved_sha:
            raise Refused("SOURCE_CHANGED_AFTER_INSPECTION")
        recipe = _recipe(raw)
        frozen = json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT source_sha,recipe FROM capability WHERE id=?",
                             (recipe["id"],)).fetchone()
            if old and old != (approved_sha, frozen):
                raise Refused("EXISTING_CAPABILITY_SOURCE_CONFLICT")
            if not old:
                db.execute("INSERT INTO capability VALUES(?,?,?,0)",
                           (recipe["id"], approved_sha, frozen))
        return {"id": recipe["id"], "source_sha256": approved_sha,
                "status": "REGISTERED_DISABLED", "auto_approved": False}

    def switch(self, name, approved_sha, enabled):
        if not isinstance(approved_sha, str) or not DIGEST.fullmatch(approved_sha):
            raise Refused("OWNER_SOURCE_SHA_REQUIRED")
        if type(enabled) is not bool:
            raise Refused("INVALID_STATE")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            n = db.execute("UPDATE capability SET enabled=? WHERE id=? AND source_sha=?",
                           (int(enabled), name, approved_sha)).rowcount
            if n != 1:
                raise Refused("CAPABILITY_OR_SHA_NOT_FOUND")
        return {"id": name, "status": "ENABLED" if enabled else "DISABLED"}

    def run(self, name, input_path):
        with self._db() as db:
            entry = db.execute("SELECT source_sha,recipe,enabled FROM capability WHERE id=?",
                               (name,)).fetchone()
        if entry is None or not entry[2]:
            raise Refused("CAPABILITY_DISABLED")
        recipe = _recipe(entry[1])
        if recipe["id"] != name:
            raise Refused("REGISTRY_CORRUPT")
        raw = _read(input_path, 65536)
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            raise Refused("INPUT_NOT_UTF8") from None
        if "\x00" in text:
            raise Refused("INPUT_BINARY_DENIED")
        needle = recipe["needle"]
        if not recipe["case_sensitive"]:
            needle = needle.casefold()
        lines, budget, truncated = [], 4096, False
        for line in text.splitlines():
            matched = line if recipe["case_sensitive"] else line.casefold()
            if needle not in matched:
                continue
            if len(lines) == recipe["limit"] or len(line) > budget:
                truncated = True
                break
            lines.append(line)
            budget -= len(line)
        return {"id": name, "source_sha256": entry[0],
                "input_sha256": hashlib.sha256(raw).hexdigest(),
                "lines": lines, "truncated": truncated, "external_actions": 0,
                "provider_calls": 0}

    def listing(self):
        with self._db() as db:
            records = db.execute("SELECT id,source_sha,enabled FROM capability ORDER BY id LIMIT 1000")
            return [{"id": x[0], "source_sha256": x[1],
                     "status": "ENABLED" if x[2] else "DISABLED"} for x in records]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register")
    reg.add_argument("--source", required=True)
    reg.add_argument("--approve-source-sha256", required=True)
    for cmd in ("enable", "disable"):
        item = sub.add_parser(cmd)
        item.add_argument("--id", required=True)
        item.add_argument("--approve-source-sha256", required=True)
    run = sub.add_parser("run")
    run.add_argument("--id", required=True)
    run.add_argument("--input", required=True)
    sub.add_parser("list")
    a = parser.parse_args()
    try:
        registry = Registry(a.db)
        if a.command == "register":
            result = registry.register(a.source, a.approve_source_sha256)
        elif a.command in ("enable", "disable"):
            result = registry.switch(a.id, a.approve_source_sha256, a.command == "enable")
        elif a.command == "run":
            result = registry.run(a.id, a.input)
        else:
            result = {"capabilities": registry.listing()}
    except (Refused, sqlite3.Error) as exc:
        code = str(exc) if isinstance(exc, Refused) else "PRIVATE_REGISTRY_UNAVAILABLE"
        print(json.dumps({"status": "BLOCKED", "error_code": code}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
