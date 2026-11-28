"""Read-only operator checks for explicitly configured ORBA Play services.

The default command validates configuration offline. Database, OAuth and Play
lookups each require an explicit flag; even a successful check never grants
access, acknowledges purchases, installs tables or accepts production.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import stat

from server.play_google_api import TOKEN_RE
from server.play_runtime import build_play_runtime, RuntimeConfigurationError
from server.play_subscription_mapper import verify_and_map_subscription

_OWNER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,100}\Z")
_COLUMNS = {
    "play_token_owners": {"token_sha256", "owner_id"},
    "play_rtdn_audit": {
        "message_digest", "payload_digest", "purchase_token_digest", "outcome",
        "recorded_at_ms",
    },
    "play_verified_snapshots": {
        "purchase_token_sha256", "product_id", "owner_hmac", "provider_state",
        "expiry_ms", "acknowledged", "historical_access", "observed_at_ms",
    },
}
_PRIMARY_KEYS = {
    "play_token_owners": {"token_sha256"},
    "play_rtdn_audit": {"message_digest"},
    "play_verified_snapshots": {"purchase_token_sha256", "product_id"},
}
_PRIVILEGES = {
    "play_token_owners": ("SELECT", "INSERT", "UPDATE"),
    "play_rtdn_audit": ("SELECT", "INSERT"),
    "play_verified_snapshots": ("SELECT", "INSERT", "UPDATE"),
}


def _result(status, code, **extra):
    return {"status": status, "code": code, **extra}


def _base_report():
    return {
        "contract": "ORBA-PLAY-PREFLIGHT-V1",
        "state": "FAILED",
        "ok": False,
        "production_acceptance": False,
        "entitlement_granted": False,
        "google_play_lookup_verified": False,
        "pubsub_oidc_verified": False,
        "checks": {
            "configuration": _result("NOT_RUN", "CONFIGURATION_NOT_CHECKED"),
            "database": _result("NOT_REQUESTED", "DATABASE_CHECK_NOT_REQUESTED"),
            "oauth": _result("NOT_REQUESTED", "OAUTH_CHECK_NOT_REQUESTED"),
            "google_play": _result("NOT_REQUESTED", "GOOGLE_PLAY_CHECK_NOT_REQUESTED"),
        },
        "blockers": [],
    }


def _fail(report, check, code, *, fields=()):
    details = {"fields": list(fields)} if fields else {}
    report["checks"][check] = _result("FAILED", code, **details)
    report["blockers"].append({"code": code, **details})
    report["state"] = "FAILED"
    report["ok"] = False


def _runtime_parts(runtime):
    boundary = runtime.play_boundary
    rtdn = runtime.rtdn_processor
    if boundary is not None:
        store, oauth = boundary._store, boundary._oauth
        products, secret = boundary._products, boundary._secret
        if rtdn is not None and store is not rtdn.store:
            raise ValueError()
    elif rtdn is not None:
        store, oauth = rtdn.store, rtdn.oauth_supplier
        products, secret = rtdn.allowed_products, rtdn.server_secret
    else:
        return None
    if (store is None or not callable(getattr(store, "db_factory", None)) or
            not callable(oauth) or not isinstance(secret, bytes) or len(secret) < 32):
        raise ValueError()
    return store, oauth, products, secret


def _purchase_token(path):
    """Bounded private-file read; never return its path in an error/report."""
    fd = None
    try:
        before = Path(path).lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        current = os.fstat(fd)
        if (not stat.S_ISREG(current.st_mode) or
                (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino) or
                stat.S_IMODE(current.st_mode) not in (0o400, 0o600) or
                (hasattr(os, "geteuid") and current.st_uid != os.geteuid())):
            raise ValueError()
        raw = os.read(fd, 4098)
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        if not 1 <= len(raw) <= 4096:
            raise ValueError()
        value = raw.decode("ascii")
        if not TOKEN_RE.fullmatch(value):
            raise ValueError()
        return value
    except Exception:
        raise ValueError("PURCHASE_TOKEN_FILE_INVALID") from None
    finally:
        if fd is not None:
            os.close(fd)


def _check_database(store):
    """Read metadata and privileges in a READ ONLY transaction; never DDL."""
    try:
        from psycopg.pq import TransactionStatus
        with closing(store.db_factory()) as connection:
            if connection.info.transaction_status != TransactionStatus.IDLE:
                return "DATABASE_SESSION_NOT_IDLE"
            with connection.transaction():
                connection.execute("SET TRANSACTION READ ONLY")
                connection.execute("SET LOCAL search_path TO pg_catalog")
                connection.execute("SET LOCAL statement_timeout = '5s'")
                connection.execute("SET LOCAL lock_timeout = '2s'")
                role = connection.execute("""SELECT rolsuper,rolcreatedb,rolcreaterole,
                    rolreplication,rolbypassrls FROM pg_catalog.pg_roles
                    WHERE rolname=current_user""").fetchone()
                if role is None or any(role):
                    return "DATABASE_ROLE_TOO_PRIVILEGED"
                schema = store.schema
                namespace = connection.execute(
                    "SELECT oid,nspowner FROM pg_catalog.pg_namespace WHERE nspname=%s",
                    (schema,),
                ).fetchone()
                if namespace is None:
                    return "DATABASE_SCHEMA_MISSING"
                if connection.execute(
                    "SELECT pg_catalog.pg_has_role(current_user,%s,'MEMBER')",
                    (namespace[1],),
                ).fetchone()[0]:
                    # Owners can alter objects or regrant their own rights
                    # even when an ACL currently denies CREATE. Membership
                    # can also permit SET ROLE independently of inheritance.
                    return "DATABASE_ROLE_OWNS_SCHEMA_OR_TABLES"
                usage, create = connection.execute("""SELECT
                    pg_catalog.has_schema_privilege(current_user,%s,'USAGE'),
                    pg_catalog.has_schema_privilege(current_user,%s,'CREATE')""",
                    (namespace[0], namespace[0]),
                ).fetchone()
                if create:
                    return "DATABASE_ROLE_CAN_CREATE_SCHEMA_OBJECTS"
                if not usage:
                    return "DATABASE_PERMISSIONS_MISSING"
                columns = connection.execute("""SELECT c.relname,a.attname,c.oid,c.relowner
                    FROM pg_catalog.pg_class c
                    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                    JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
                    WHERE n.nspname=%s AND c.relname=ANY(%s)
                    AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped""",
                    (schema, list(_COLUMNS)),
                ).fetchall()
                available, identifiers, owner_roles = {}, {}, set()
                for table, column, oid, owner_role in columns:
                    available.setdefault(table, set()).add(column)
                    identifiers[table] = oid
                    owner_roles.add(owner_role)
                if set(available) != set(_COLUMNS):
                    return "DATABASE_TABLES_MISSING"
                for owner_role in owner_roles:
                    if connection.execute(
                        "SELECT pg_catalog.pg_has_role(current_user,%s,'MEMBER')",
                        (owner_role,),
                    ).fetchone()[0]:
                        return "DATABASE_ROLE_OWNS_SCHEMA_OR_TABLES"
                if any(not required <= available[table]
                       for table, required in _COLUMNS.items()):
                    return "DATABASE_COLUMNS_MISSING"
                keys = connection.execute("""SELECT c.relname,
                    pg_catalog.array_agg(a.attname ORDER BY k.ord)
                    FROM pg_catalog.pg_index i
                    JOIN pg_catalog.pg_class c ON c.oid=i.indrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                    CROSS JOIN LATERAL pg_catalog.unnest(i.indkey)
                        WITH ORDINALITY AS k(attnum,ord)
                    JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
                    WHERE i.indisprimary AND n.nspname=%s AND c.relname=ANY(%s)
                    GROUP BY c.relname""", (schema, list(_COLUMNS))).fetchall()
                primary = {table: set(names) for table, names in keys}
                if primary != _PRIMARY_KEYS:
                    return "DATABASE_PRIMARY_KEYS_MISSING"
                for table, permissions in _PRIVILEGES.items():
                    for permission in permissions:
                        granted = connection.execute(
                            "SELECT pg_catalog.has_table_privilege(current_user,%s,%s)",
                            (identifiers[table], permission),
                        ).fetchone()[0]
                        if granted is not True:
                            return "DATABASE_PERMISSIONS_MISSING"
        return None
    except Exception:
        return "DATABASE_CHECK_UNAVAILABLE"


def preflight(*, environ=None, check_database=False, check_oauth=False,
              check_google=False, purchase_token_file=None, product=None,
              runtime_builder=build_play_runtime, opener=None):
    """Return a non-sensitive report for the checks explicitly requested.

    ``ok`` refers only to these checks. Production acceptance remains false.
    ``runtime_builder`` and ``opener`` are trusted offline test seams.
    """
    report = _base_report()
    env = os.environ if environ is None else environ
    try:
        runtime = runtime_builder(environ=env)
    except RuntimeConfigurationError as error:
        code = error.code if isinstance(error.code, str) and _SAFE_CODE.fullmatch(
            error.code) else "PLAY_RUNTIME_CONFIGURATION_INVALID"
        fields = tuple(name for name in error.fields
                       if isinstance(name, str) and _SAFE_CODE.fullmatch(name))
        _fail(report, "configuration", code, fields=fields)
        return report
    except Exception:
        _fail(report, "configuration", "PLAY_RUNTIME_BUILD_FAILED")
        return report
    try:
        parts = _runtime_parts(runtime)
    except Exception:
        _fail(report, "configuration", "PLAY_RUNTIME_DEPENDENCIES_INVALID")
        return report
    if parts is None:
        report["state"] = "DISABLED"
        fields = ["ORBA_PLAY_BOUNDARY_ENABLED", "ORBA_PLAY_RTDN_ENABLED"]
        report["checks"]["configuration"] = _result(
            "DISABLED", "PLAY_RUNTIME_DISABLED", fields=fields)
        report["blockers"].append({"code": "PLAY_RUNTIME_DISABLED", "fields": fields})
        return report
    report["checks"]["configuration"] = _result("PASS", "PLAY_RUNTIME_CONFIGURED")
    store, oauth, products, secret = parts
    google_requested = check_google or purchase_token_file is not None or product is not None
    oauth_requested = check_oauth or google_requested
    purchase_token, owner = None, None
    if google_requested:
        if purchase_token_file is None:
            _fail(report, "google_play", "PURCHASE_TOKEN_FILE_REQUIRED")
            return report
        if not isinstance(product, str) or product not in products:
            _fail(report, "google_play", "GOOGLE_PLAY_PRODUCT_NOT_ALLOWED")
            return report
        owner = env.get("OMEGA_OWNER_ID")
        if not isinstance(owner, str) or not _OWNER.fullmatch(owner):
            _fail(report, "google_play", "GOOGLE_PLAY_OWNER_NOT_CONFIGURED",
                  fields=("OMEGA_OWNER_ID",))
            return report
        try:
            purchase_token = _purchase_token(purchase_token_file)
        except ValueError:
            _fail(report, "google_play", "PURCHASE_TOKEN_FILE_INVALID")
            return report
    if check_database:
        code = _check_database(store)
        if code:
            _fail(report, "database", code)
        else:
            report["checks"]["database"] = _result(
                "PASS", "DATABASE_READ_ONLY_CHECKS_PASSED")
    access_token = None
    if oauth_requested:
        try:
            access_token = oauth()
            if (not isinstance(access_token, str) or not 1 <= len(access_token) <= 8192 or
                    not access_token.isascii() or
                    any(ord(c) <= 32 or ord(c) >= 127 for c in access_token)):
                raise ValueError()
        except Exception:
            _fail(report, "oauth", "PUBLISHER_OAUTH_CHECK_UNAVAILABLE")
            if google_requested:
                report["checks"]["google_play"] = _result(
                    "NOT_RUN", "GOOGLE_PLAY_OAUTH_REQUIRED")
        else:
            report["checks"]["oauth"] = _result("PASS", "PUBLISHER_OAUTH_OBTAINED")
    if google_requested and access_token is not None and report["checks"]["oauth"]["status"] == "PASS":
        try:
            verified = verify_and_map_subscription(
                purchase_token=purchase_token, access_token=access_token,
                owner_id=owner, product_id=product, server_secret=secret, opener=opener)
            if verified.verified_by_google_api is not True:
                raise ValueError()
        except Exception:
            _fail(report, "google_play", "GOOGLE_PLAY_LOOKUP_UNAVAILABLE")
        else:
            report["checks"]["google_play"] = _result("PASS", "GOOGLE_PLAY_OWNER_LOOKUP_VERIFIED")
            report["google_play_lookup_verified"] = True
    if not report["blockers"]:
        report["state"] = "CHECKED" if check_database or oauth_requested else "CONFIGURED"
        report["ok"] = True
    return report


def main(argv=None, *, environ=None, runtime_builder=build_play_runtime):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-database", action="store_true",
                        help="read-only PostgreSQL schema/privilege checks")
    parser.add_argument("--check-oauth", action="store_true",
                        help="explicitly obtain OAuth without exposing the access token")
    parser.add_argument("--check-google", action="store_true",
                        help="read-only owner-matched Play GET; requires token file and product")
    parser.add_argument("--purchase-token-file",
                        help="private 0600/0400 regular file; implies --check-google")
    parser.add_argument("--product", help="configured product for the read-only Play check")
    args = parser.parse_args(argv)
    report = preflight(environ=environ, runtime_builder=runtime_builder, **vars(args))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
