# MyApp — Android release-candidate build

This subdirectory is isolated from the existing GPTAsistan Android app in this repository. The GitHub Actions workflow at `.github/workflows/myapp-apk.yml` builds and uploads a separately signed `com.example.myapp` APK candidate.

## Test-only CI signing
Each CI run creates a **new ephemeral signing key** that is deliberately not uploaded. The resulting APK is for verification/testing only: you cannot install an update over an older APK signed by a different CI run. Do not publish it as a production release. For production signing, build with your persistent private keystore held offline and inject KEYSTORE_PATH, KEYSTORE_PASS, KEY_ALIAS and KEY_PASS as secure environment variables.

Requirements for a local build: JDK 17, Gradle 8.7, Android SDK Platform 34 and Build Tools 34.0.0. Build with `gradle clean assembleRelease` after setting signing credentials.

This demo launcher does not implement a foreground service or notification behavior. Declaring permissions does not implement those features.
