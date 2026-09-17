---
name: apk-forensic
description: Evidence-driven read-only Android APK/APKM and Flutter/Dart AOT forensic workflow. Use for artifact identity, signing, manifest, DEX, ELF/native libraries, Flutter libapp.so, ObjectPool/xrefs, endpoints, crypto call chains, and reproducible forensic evidence.
allowed-tools:
  - read
  - search
  - execute
---

# APK Forensic Skill

Work only on an analysis copy. Hash the original with SHA-256 and SHA-512 before and after analysis and prove preservation.

Use the strongest available toolchain and record exact versions and return codes: `jadx`, `apktool`, `apksigner`, `bundletool`, `aapt2`/`apkanalyzer`, Androguard, `readelf`, `objdump`, `nm`, `strings`, OpenSSL, keytool, Ghidra headless, Capstone, radare2, r2flutter and Blutter.

For APKM, enumerate every physical APK and classify base/config ABI/density/language/feature splits before interpreting app behavior.

For native/Flutter targets, extract only temporary copies of `.so` files. Determine ABI and ELF metadata before deeper analysis. For Dart AOT, prefer exact snapshot-version detection; when the evidence independently establishes a Dart version such as 3.10.7, use the matching r2flutter profile and record whether the version was exact-hash detected or manually overridden.

For ObjectPool/xref work, keep a traceable chain from pool entry/address to xrefs/caller/function and then to higher-level operation. For security-sensitive findings such as RSA keys, tokens, access tokens or credentials, do not print the secret value. Record only safe fingerprints, locations and call relationships.

Classify conclusions as CONFIRMED_STATIC_FACT, INDICATOR, HYPOTHESIS, RUNTIME_VERIFIED, or NOT_TESTED. Static strings do not prove runtime use.

Do not repeat already verified inventory as new progress. Focus on unresolved call chains, request builders, system-prompt flow, access-token storage/backend, model-routing branches, PairIP semantics and remaining blobs when those are the active gates.
