# KRAL 4.6–4.13: local reuse milestone (10 November 2026)

Authoritative roadmap requires recovery choice, verified permissions, tests,
controlled activation and reuse in an independent later task.

This new module adds ONLY a narrow safe deterministic capability:
an owner-selected declarative JSON recipe for filtering lines of text.
No code in the source is executed. This is not APK feature extraction,
a live model, provider fallback or autonomous Android task execution.

Example JSON recipe:

    {"version":1,"id":"status.filter","operation":"text.filter_lines",
     "needle":"ERROR","case_sensitive":false,"limit":5}

Step 1. Run python3 -m server.source_intake /private/recipe.json
Step 2. Independently obtain the selected recipe's SHA-256.
Step 3. Register, always disabled by default:

    python3 -m server.capability_lifecycle --db /private/local.sqlite3 register --source /private/recipe.json --approve-source-sha256 SHA64

Step 4. After local operator review explicitly enable:

    python3 -m server.capability_lifecycle --db /private/local.sqlite3 enable --id status.filter --approve-source-sha256 SHA64

Step 5. Reuse in a later separate task/process with a new input file:

    python3 -m server.capability_lifecycle --db /private/local.sqlite3 run --id status.filter --input /private/another-task.log

Step 6. Roll back safely:

    python3 -m server.capability_lifecycle --db /private/local.sqlite3 disable --id status.filter --approve-source-sha256 SHA64

Exact SHA match is a local operator selection; it is NOT proof of P-256 owner
identity. Database is local chmod 0600. No secret, OAuth, network, service,
provider request, arbitrary script, archive or APK is executed by this module.

Tests cover real local fixture files, independent second task, database reopen,
rollback, digest mismatch, malformed recipes, symlink/ZIP and bounds.
The original source is preserved. This module does not register a live external
capability or alter production. T06/T07 real owner-APK acceptance stays blocked.
All physical device, release signer, live provider, final T01–T26 and Drive
redownload acceptance gates remain outstanding.
