# ORBA RTDN transaction storage

This change extends the actual `Gpt-asistan` source at commit
`dd08a2b70e28005e3afb62f5fe035e7212c63798` (14 November 2026 RTDN reconciliation
branch). The separately described OMEGA V41 ZIP was unavailable. These tests
are new regressions; they are not the 16 skipped tests in that package.

## Behavior

Google OIDC authentication, configured subscription/package checks, fresh Play
API verification and owner HMAC verification still run before accepting a new
subscription notification. RTDN remains a signal to recheck Google; no event
type or stored snapshot grants access.

`PlayRtdnProcessor` now uses a delivery transaction. SQLite acquires its writer
lock before checking for duplicates. PostgreSQL acquires a transaction advisory
lock per delivery before checking its durable audit table. A concurrent exact
duplicate waits and then sees the committed result without calling Google
again. A changed payload under the same delivery ID is rejected.

Provider evidence and the success audit commit together. A failed provider
call, snapshot write, audit insert or commit leaves no success acknowledgment.
Pub/Sub may retry. A Google GET that happened before a rollback or process
crash may be repeated on retry: this is not an exactly-once guarantee for
external operations. Google calls here are read-only.

The digest now includes the configured Pub/Sub subscription and message ID.
Existing SQLite rows made with the old ID-only digest are retained. A redelivery
of an old row after upgrade may cause one fresh authenticated Google recheck;
it cannot grant access from the old notification. Keep the same subscription
name and durable schema across worker restarts.

## Explicit PostgreSQL configuration

Install `server/requirements-postgres.txt` in addition to the server requirements.
The trusted installer calls `initialize_postgres_rtdn(connection, schema=...)`
on an idle connection once. Request handlers never create or migrate tables.
Use a dedicated private schema and a runtime role with table access but without
schema creation or general administrative permissions.

```python
from functools import partial
import psycopg
from server.play_rtdn import PlayRtdnProcessor
from server.play_rtdn_postgres import PostgresRtdnStore, record_postgres_snapshot

# Read these from the trusted deployment's existing configuration/secret store.
def connection_factory():
    return psycopg.connect(database_dsn, autocommit=True, connect_timeout=5)

processor = PlayRtdnProcessor(
    audience=push_audience,
    service_account_email=push_service_account,
    subscription=pubsub_subscription,
    allowed_products=allowed_products,
    server_secret=server_secret,
    oauth_supplier=publisher_oauth_supplier,
    store=PostgresRtdnStore(connection_factory, schema="orba"),
    snapshot_recorder=partial(record_postgres_snapshot, schema="orba"),
)
```

Inject this processor through the existing gateway's `rtdn_processor` argument.
Its existing path is `POST /api/v1/play/rtdn`; it remains disabled by default.
This recovered source uses the standard-library gateway, not the unavailable
V41 FastAPI `/api/v1/orba/pubsub/push` implementation.

`db_factory` and explicit `store` are mutually exclusive. Every factory call
must return a fresh idle connection. All workers must use the same database
and schema for the same subscription. The store enforces READ COMMITTED so
waiters see the preceding worker's committed audit. Lock waits are bounded
at 10 seconds; provider and connection timeouts must also remain bounded.
PostgreSQL observations use the database clock immediately before the Google
recheck, so different worker wall clocks do not determine snapshot order.
Conflicting observations at the same millisecond still fail closed and retry.
Custom snapshot recorders must participate in the supplied transaction and
must not commit it independently.

The PostgreSQL owner table is separate from the existing SQLite purchase
gateway's owner ledger. There is no automatic owner migration or new binding
endpoint. A trusted verified-purchase service must provision ownership in the
same database before RTDN can record an owner-bound snapshot. Unbound tokens
are audited without binding a user or writing an owner snapshot. This adapter
does not migrate the purchase gateway, Android billing or payment collection.

## Verification

Existing offline server tests still run without PostgreSQL:

```sh
python -m unittest discover -s server/tests -v
```

Run the new real-database suite in a disposable container:

```sh
python -m pip install -r server/requirements.txt -r server/requirements-postgres.txt
bash scripts/test_orba_rtdn_postgres.sh
```

Set `ORBA_TEST_PYTHON` if the dependencies are in a virtual environment. The
runner creates a new PostgreSQL 16 container with a temporary data filesystem,
a generated test password and an ephemeral loopback port, and removes it on
exit. It never accepts an existing database DSN. Direct execution of the
integration test module requires an explicit loopback `orba_test` DSN and
fails rather than skipping when that database is missing. Each test creates
and drops its own randomly named schema.

The integration suite includes a real localhost HTTP gateway backed by
PostgreSQL: authenticated delivery and duplicate responses, rejection before
database access on invalid authentication, and HTTP 503 with atomic rollback
when the success audit cannot be written. Google responses remain synthetic.

Real Google OIDC/provider responses, Play Console authorization, Android
license-test purchases, production ownership migration and public deployment
are not established by these tests. The historical 100-item OMEGA acceptance
remains open.
