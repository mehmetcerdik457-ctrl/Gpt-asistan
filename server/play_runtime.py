"""Explicit, fail-closed Play runtime construction; never installs a schema.

Building the runtime validates configuration and wires lazy dependencies only.
It does not read ADC, connect to PostgreSQL, fetch Google, or open a listener.
"""
from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import partial
import ipaddress
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from server.play_entitlement_gate import PACKAGE, PRODUCT_RE
from server.play_google_oauth import PlayPublisherOAuth, SERVICE_ACCOUNT_PATTERN

_FLAGS = ("ORBA_PLAY_BOUNDARY_ENABLED", "ORBA_PLAY_RTDN_ENABLED", "ORBA_PLAY_OAUTH_ENABLED")
_COMMON = (
    "ORBA_PLAY_DATABASE_DSN", "ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT",
    "ORBA_PLAY_PRODUCTS", "ORBA_PLAY_PACKAGE", "ORBA_PLAY_SERVER_SECRET_B64",
)
_PUBSUB = (
    "ORBA_PLAY_PUBSUB_AUDIENCE", "ORBA_PLAY_PUBSUB_SERVICE_ACCOUNT",
    "ORBA_PLAY_PUBSUB_SUBSCRIPTION",
)
_OWNER = (
    "OMEGA_OWNER_ID", "OMEGA_DEVICE_ID", "OMEGA_OWNER_PUBLIC_DER_B64",
    "OMEGA_DEVICE_PUBLIC_DER_B64", "OMEGA_NONCE_DB",
)
_PG_SELECTORS = (
    "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR", "PGOPTIONS",
    "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGSSLMODE",
)
_SCHEMA = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
_DNS = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?\Z"
)
_SUBSCRIPTION = re.compile(
    r"projects/[A-Za-z0-9_.~+%-]{1,128}/subscriptions/[A-Za-z0-9_.~+%-]{1,128}\Z"
)


class RuntimeConfigurationError(RuntimeError):
    """Fixed error codes and field names only; never configuration values."""
    def __init__(self, code, fields=()):
        self.code = code
        self.fields = tuple(fields)
        super().__init__(code + (":" + ",".join(self.fields) if self.fields else ""))


@dataclass(frozen=True)
class PlayRuntime:
    play_boundary: object | None = field(default=None, repr=False)
    rtdn_processor: object | None = field(default=None, repr=False)


def _invalid(*names):
    raise RuntimeConfigurationError("PLAY_RUNTIME_CONFIGURATION_INVALID", names) from None


def _required(environ, names):
    missing = tuple(name for name in names
                    if not isinstance(environ.get(name), str) or not environ[name].strip())
    if missing:
        raise RuntimeConfigurationError("PLAY_RUNTIME_CONFIGURATION_MISSING", missing)


def _reject_database_overrides(environ):
    # libpq reads its process environment in addition to the DSN. Reject
    # target selectors even with an injected configuration mapping so a
    # PGHOSTADDR/service/options override cannot redirect an approved target.
    conflicting = tuple(name for name in _PG_SELECTORS
                        if name in environ or name in os.environ)
    if conflicting:
        raise RuntimeConfigurationError("PLAY_RUNTIME_DATABASE_ENVIRONMENT_CONFLICT", conflicting)


def _secret(value):
    name = "ORBA_PLAY_SERVER_SECRET_B64"
    if (not isinstance(value, str) or len(value) > 8192 or
            not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value)):
        _invalid(name)
    try:
        secret = base64.b64decode(value + "=" * (-len(value) % 4),
                                  altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        _invalid(name)
    if (not 32 <= len(secret) <= 4096 or
            base64.urlsafe_b64encode(secret).decode().rstrip("=") != value.rstrip("=")):
        _invalid(name)
    return secret


def _database_dsn(value):
    """Validate libpq configuration without a socket or credential lookup."""
    name = "ORBA_PLAY_DATABASE_DSN"
    if (not isinstance(value, str) or not 1 <= len(value) <= 8192 or
            value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value) or
            ("://" in value and not value.startswith(("postgresql://", "postgres://")))):
        _invalid(name)
    try:
        from psycopg.conninfo import conninfo_to_dict
    except ImportError:
        raise RuntimeConfigurationError("PLAY_RUNTIME_POSTGRES_DEPENDENCY_MISSING") from None
    try:
        settings = conninfo_to_dict(value)
    except Exception:
        _invalid(name)
    if any(any(ord(c) < 32 or ord(c) == 127 for c in item)
           for item in settings.values()):
        _invalid(name)
    # Explicit host/user/database prevent ambient PG* defaults from selecting
    # another target. Multiple hosts, service files and startup options are not
    # accepted by this initial runtime policy.
    if any(key in settings for key in ("service", "servicefile", "hostaddr", "options")):
        _invalid(name)
    host = settings.get("host", "")
    if (not host or any(c.isspace() for c in host) or "," in host or
            any(not settings.get(key) or "://" in settings[key] or
                any(c.isspace() for c in settings[key])
                for key in ("user", "dbname"))):
        _invalid(name)
    try:
        address = ipaddress.ip_address(host)
        loopback = address.is_loopback
    except ValueError:
        if not _DNS.fullmatch(host):
            _invalid(name)
        loopback = host.lower() == "localhost"
    port = settings.get("port")
    if port is not None and (not port.isascii() or not port.isdecimal() or
                             not 1 <= int(port) <= 65535):
        _invalid(name)
    if not loopback and settings.get("sslmode") != "verify-full":
        _invalid(name)
    return value


def _owner_configuration(environ):
    _required(environ, _OWNER)
    try:
        from server.enroll import validated_env
        validated_env({
            "contract": "OMEGA-OWNER-API-V1",
            "owner_id": environ["OMEGA_OWNER_ID"],
            "device_id": environ["OMEGA_DEVICE_ID"],
            "owner_public_der_b64": environ["OMEGA_OWNER_PUBLIC_DER_B64"],
            "device_public_der_b64": environ["OMEGA_DEVICE_PUBLIC_DER_B64"],
        })
    except Exception:
        _invalid(*_OWNER[:4])
    try:
        path = Path(environ["OMEGA_NONCE_DB"])
        valid = (path.is_absolute() and path.parent.is_dir() and not path.is_symlink()
                 and (not path.exists() or path.is_file()))
    except (OSError, ValueError, TypeError):
        valid = False
    if not valid:
        _invalid("OMEGA_NONCE_DB")


def _pubsub_configuration(environ):
    _required(environ, _PUBSUB)
    audience = environ[_PUBSUB[0]]
    try:
        parts = urlsplit(audience)
        valid = (len(audience) <= 400 and not any(c.isspace() or ord(c) < 33 for c in audience)
                 and parts.scheme == "https" and bool(parts.hostname)
                 and parts.username is None and parts.password is None
                 and not parts.query and not parts.fragment
                 and (parts.port is None or 1 <= parts.port <= 65535))
        if valid:
            try:
                ipaddress.ip_address(parts.hostname)
            except ValueError:
                valid = _DNS.fullmatch(parts.hostname) is not None
    except (ValueError, TypeError):
        valid = False
    if not valid:
        _invalid(_PUBSUB[0])
    if not SERVICE_ACCOUNT_PATTERN.fullmatch(environ[_PUBSUB[1]]):
        _invalid(_PUBSUB[1])
    if not _SUBSCRIPTION.fullmatch(environ[_PUBSUB[2]]):
        _invalid(_PUBSUB[2])


def build_play_runtime(environ=None, *, connect_factory=None, oauth_factory=None):
    """Return disabled components unless complete opt-in configuration passes.

    ``connect_factory`` accepts the psycopg.connect signature and is called
    lazily with autocommit=True and connect_timeout=5. ``oauth_factory`` accepts
    PlayPublisherOAuth constructor keywords; constructing it must not load ADC.
    """
    env = os.environ if environ is None else environ
    if not isinstance(env, Mapping):
        raise RuntimeConfigurationError("PLAY_RUNTIME_ENVIRONMENT_INVALID")
    invalid_flags = tuple(name for name in _FLAGS
                          if env.get(name, "NO") not in ("YES", "NO"))
    if invalid_flags:
        _invalid(*invalid_flags)
    boundary_enabled = env.get(_FLAGS[0]) == "YES"
    rtdn_enabled = env.get(_FLAGS[1]) == "YES"
    if not boundary_enabled and not rtdn_enabled:
        return PlayRuntime()
    if env.get("ORBA_PLAY_OAUTH_ENABLED") != "YES":
        _invalid("ORBA_PLAY_OAUTH_ENABLED")
    _reject_database_overrides(env)
    _required(env, _COMMON)
    if env["ORBA_PLAY_PACKAGE"] != PACKAGE:
        _invalid("ORBA_PLAY_PACKAGE")
    products = env["ORBA_PLAY_PRODUCTS"].split(",")
    if (not all(PRODUCT_RE.fullmatch(product) for product in products) or
            len(products) != len(set(products))):
        _invalid("ORBA_PLAY_PRODUCTS")
    schema = env.get("ORBA_PLAY_DATABASE_SCHEMA", "orba")
    if (not isinstance(schema, str) or not _SCHEMA.fullmatch(schema) or
            schema.startswith("pg_") or schema == "information_schema"):
        _invalid("ORBA_PLAY_DATABASE_SCHEMA")
    if not SERVICE_ACCOUNT_PATTERN.fullmatch(env["ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT"]):
        _invalid("ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT")
    secret = _secret(env["ORBA_PLAY_SERVER_SECRET_B64"])
    if boundary_enabled:
        _owner_configuration(env)
    if rtdn_enabled:
        _pubsub_configuration(env)
    dsn = _database_dsn(env["ORBA_PLAY_DATABASE_DSN"])
    if ((connect_factory is not None and not callable(connect_factory)) or
            (oauth_factory is not None and not callable(oauth_factory))):
        raise RuntimeConfigurationError("PLAY_RUNTIME_DEPENDENCY_INVALID")
    try:
        # Optional dependencies are imported only after explicit activation.
        import psycopg
        from server.play_gateway_boundary import PlayGatewayBoundary
        from server.play_purchase_postgres import PostgresPlayStore
        from server.play_rtdn import PlayRtdnProcessor
        from server.play_rtdn_postgres import record_postgres_snapshot
    except ImportError:
        raise RuntimeConfigurationError("PLAY_RUNTIME_POSTGRES_DEPENDENCY_MISSING") from None
    connector = connect_factory if connect_factory is not None else psycopg.connect

    def db_factory():
        # Check again immediately before libpq can consult ambient settings;
        # successful startup validation must not authorize later redirection.
        _reject_database_overrides(env)
        return connector(dsn, autocommit=True, connect_timeout=5)

    try:
        oauth = (oauth_factory if oauth_factory is not None else PlayPublisherOAuth)(
            service_account_email=env["ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT"],
            enabled=lambda: env.get("ORBA_PLAY_OAUTH_ENABLED") == "YES",
        )
        if not callable(oauth):
            raise ValueError()
        store = PostgresPlayStore(db_factory, schema=schema)
        boundary = PlayGatewayBoundary(
            store=store, server_secret=secret, allowed_products=set(products),
            oauth_supplier=oauth,
        ) if boundary_enabled else None
        rtdn = PlayRtdnProcessor(
            audience=env["ORBA_PLAY_PUBSUB_AUDIENCE"],
            service_account_email=env["ORBA_PLAY_PUBSUB_SERVICE_ACCOUNT"],
            subscription=env["ORBA_PLAY_PUBSUB_SUBSCRIPTION"],
            allowed_products=set(products), server_secret=secret,
            store=store, oauth_supplier=oauth,
            snapshot_recorder=partial(record_postgres_snapshot, schema=schema),
        ) if rtdn_enabled else None
        return PlayRuntime(boundary, rtdn)
    except Exception:
        raise RuntimeConfigurationError("PLAY_RUNTIME_INITIALIZATION_FAILED") from None
