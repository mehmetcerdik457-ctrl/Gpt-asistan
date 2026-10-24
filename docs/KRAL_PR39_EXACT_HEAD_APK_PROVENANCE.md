# KRAL PR39 — exact-HEAD APK provenance correction

Source branch `integration/cihat-github-task-bridge-20261021` original HEAD
`f252d2499d39565ad3f4c78c2cf2fac7e606c9b9`.

2026-10-22 Android workflow 39810659627 produced a signed debug preview APK,
but its metadata `source_commit` was the GitHub PR synthetic merge SHA
`78cdd5fbfbd43f6354adad2a7b70ea62534ccf50`. Actual PR39 HEAD was
`f252d2499d39565ad3f4c78c2cf2fac7e606c9b9`. These two commits had the exact same Git tree
`68962cf1a9558fc69afdb191ff644cdb2ede3170`, so code *bytes* matched,
but exact commit provenance was misleading. Artifact SHA-256:
`529791906f829b2e36b1a1d703af5030dfb46689d411bf4b52b4f08817380dcb`.
It was debug-signed under preview package
`com.example.gptasistan.genesis.cihatpreview`, **not** the historical
Owner/CİHAT signer and **not** an actual phone validation.

The fix makes all Android build/emulator and Python CI checkouts select the
exact event PR head SHA, asserts `git rev-parse HEAD` equals it, and binds
the emulator smoke's evidence to the checked-out SHA instead of a synthetic
`GITHUB_SHA`. New unit tests fail if this contract regresses.
No existing Android project, package or signed APK was rewritten.

This change alone is not a successful candidate build. Acceptance requires
**new CI build and emulator success on the exact new commit**, artifact
metadata matching the exact GitHub PR head, APK SHA-256, signature validation,
emulator install/launch, and physical phone review before release.
