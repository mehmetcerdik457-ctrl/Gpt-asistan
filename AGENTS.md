# AGENTS.md

This repository expects agents to work like senior engineers, not autocomplete.

## Mission
Inspect first, change second, verify third. Finish implementation tasks end-to-end whenever repository and tool permissions allow.

## Required workflow
1. Inspect the relevant code, configuration, workflows, and tests.
2. State internally what evidence is missing before editing.
3. Make minimal coherent changes.
4. Run relevant verification and inspect real output.
5. Fix regressions or clearly document blockers.
6. Report changed files and evidence.

## Safety and integrity
- Never fabricate successful builds, tests, signatures, hashes, runtime behavior, device evidence, or CI status.
- Never expose or commit secrets.
- Never bypass branch protection, code review, or security controls just to make progress.
- Do not rewrite Git history or delete releases/tags/branches unless explicitly requested.
- Keep Android signing material outside source control.

## Android focus
Check Gradle compatibility, manifest declarations, exported components, permissions, target-SDK behavior, lifecycle issues, coroutine cancellation, network security, storage, WebView risk, notification behavior, and background execution when relevant.

## Completion rule
A task is not complete merely because code was written. It is complete only when the strongest available verification has been attempted and the result is reported truthfully.
