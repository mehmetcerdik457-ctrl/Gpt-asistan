# Master roadmap

1. **Local foundation (implemented):** safe CLI, SQLite memory, JSON backup,
   offline-first core, and tests.
2. **Local inference (NOT DONE):** select a compatible runtime and model only
   after device testing, license review, and memory/performance measurement.
3. **Android application (NOT DONE):** confirm Android sources/resources,
   define UI and storage ownership, and verify builds on-device.
4. **Cloud integrations (NOT DONE):** consider Google Drive and YouTube only
   as opt-in features with explicit credential and privacy controls.
5. **Release readiness:** test restore/deletion workflows, document supported
   devices, and verify all platform builds and security controls.

The Android build is currently unverified because `MainActivity.kt` and
`res` resources are not confirmed present.
