# KRAL SQLCipher – Non-destructive migration acceptance

**Scope:** experimental `integration/kral-local-db-encryption-20261021` lineage only.
**Status:** draft / no deployment / no merge into production APK.

## What changed

The migration supports an existing local **plaintext SQLite v1 or v2** database and creates a
version-3 SQLCipher database in a staging file. Before replacing the active name it
checks source SQLite integrity, source row counts, encrypted staging integrity and
row counts. It subsequently verifies the active encrypted database once more.
No original database is automatically deleted.

## Fail-closed conditions

- Unknown DB format, incorrect SQLCipher key or incomplete schema.
- Previously interrupted staging or legacy file when the main DB is plaintext.
- Any source `-wal`, `-shm` or `-journal` sidecar: this migration does **not**
  silently checkpoint the source or assume the sidecars are disposable.
- Source `quick_check` or post-export `quick_check`/table-count mismatch.
- Failure to rename source or activate encrypted staging.

These conditions require forensic review and an owner-authorized recovery plan.
Never remove sidecars or legacy/staging files simply to make the guard pass.

## Important privacy caveat

After a successful conversion, the original source is retained as
`kral_local.db.plaintext-legacy` for recovery. **This is plaintext sensitive data.**
While that file exists, **whole-app encryption at rest is NOT complete**. This
behavior is deliberate to avoid data loss; it is **not** an accepted production
retention strategy. The original must only be handled under a separately approved,
verified secure backup/retention/cleanup procedure.

The original local database and a historical Termux `mem.db` are separate; this
migration does not import or modify the Termux file.

## Required acceptance before integration into the API 36 candidate

1. CI: Android build and connected emulator instrumentation tests, including
   a fresh DB, legacy v1 and v2, SQLite WAL/journal refusal, interrupted staging,
   incorrect key, row preservation, restart and recovery.
2. API 30 and API 36 emulator: real SQLCipher native library, record the expected
   version, test that old and encrypted databases never overwrite each other.
3. Fault injection: migration interrupted at export, source rename, staging
   rename and final verification. Prove source data are still recoverable.
4. Physical device: user-approved, **offline backup first**, controlled migration,
   application reopen and data comparison. No real user content in CI logs.
5. Release owner review: manage remaining plaintext legacy copy, identity key
   availability, storage pressure and backup policies; then build/sign a new AAB.
6. Reconcile with the later Android/Kotlin/API36/worker-response branches.
   This draft does not claim those branches are integrated.

## Evidence discipline

A build or debug APK only proves compilation. A passing emulator smoke test
only proves the tests exercised. No release signing, live provider, Play Console
upload, owner enrollment, physical phone migration or deletion is authorized here.
