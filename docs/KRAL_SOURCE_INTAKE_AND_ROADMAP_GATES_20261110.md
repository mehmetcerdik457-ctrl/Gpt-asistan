# KRAL safe source intake and roadmap acceptance gates

## Scope and use

This branch adds an actual **read-only local-file scanner** for the first
stages of 4.1–4.5 of the user's 13-stage source acquisition roadmap.
It does not claim source acquisition 4.6–4.13 is complete.

After legitimately obtaining the owner's selected APK, AAB, ZIP, GGUF or other
local file onto an authorized computer, run:

```bash
python3 -m server.source_intake /path/to/authorized.apk
```

The scanner:
- Opens only explicitly listed regular files, rejecting symlinks;
- Computes SHA-256 twice and verifies original inode/size/timestamps were stable;
- Statically inspects ZIP/APK/AAB paths and ABI *path claims* under strict limits;
- Rejects archive traversal, symlinks, duplicate paths, unsafe entry counts,
  inflated-size abuse, and suspicious compression ratios;
- Never executes or extracts untrusted code, uses OAuth, reads Android Keystore,
  sends prompts to an LLM or declares a runnable capability.
- Reports `ANALYZED_STATIC_ONLY`, not `CONNECTED` or `TESTED`.
- Does **not** verify APK signatures, manifest contents/package, application
  license, real model weights or local runner functionality.
- Does not automatically recurse through the 207 Drive APK *metadata* records;
  actual APK bytes must be independently and lawfully supplied.

## Roadmap evidence validator

```bash
python3 -m server.roadmap_evidence --target-commit "$(git rev-parse HEAD)"
```

The validator reads eleven legacy JSON manifests, checks the **exact**
T01–T26 set and order, and reports stale commit binding. It never promotes old
CI/test counts or the 2026-11-04 acceptance document to final PASS.

The baseline audited commit `29021cfe71cbcd3cb54b449dd65f708a3876204a`
had [237/237 Python tests and successful API30/36 emulator builds](
https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/42531599641).
Its APK's SHA-256 was
`886281f91e9aa1df62a12548cad7080edc0def5fefb32c5aff89f7fba706325d`.
This immutable **prior commit evidence is not automatically a passing result for
this branch's newly written HEAD**. This branch must have its own tests.

## Remaining owner and provider boundaries

- No connected physical Android device or installed signer identity was verified.
- No owner-signed release, safe upgrade, or owner credential was generated.
- No live OpenAI/Gemini/local model was called; no API usage charges.
- No fresh Drive upload and re-download SHA-256 for a final APK.
- No YouTube publishing or payments.
- Nothing is merged into `main`; final 0–28 and T01–T26 remain blocked until
  independently witnessed actual results are recorded against exact source.

Practical next stage: provide *one authorized APK file* to this scanner, verify
package/signature with a separate trusted Android SDK tool, then map any usable
API/SDK capability into the KRAL registry only after 4.6–4.13 tests.
