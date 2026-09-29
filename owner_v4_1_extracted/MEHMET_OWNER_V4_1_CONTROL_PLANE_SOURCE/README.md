# MEHMET OWNER V4.1 CONTROL PLANE — SOURCE CANDIDATE

OWNER = MEHMET CERDİK

V4 immutable baseline korunur. V4.1 ayrı adaydır. Current vendor worker `com.codespaceapps.aichat` 3.2.1/893 ve 7B4A signer ile değiştirilmeden kalır.

## Gerçek kapsam

Bu aday **AI autonomous phone agent değildir**. Bu, owner-controlled Android action surface + güvenlik control-plane kaynağıdır. `ANLA` / LLM ToolBus karar döngüsü ayrı açık mimari gate'tir.

Bridge yüzeyi: screenRead, exact click, type, scroll, normalized swipe, Back/Home/Recents/Notifications, package launch, explicit target postcondition verify.

## V4.1 güvenlik değişiklikleri

- Arm TTL wall-clock'tan çıkarıldı; `SystemClock.elapsedRealtime()` + process ID + process-session + boot-count ile process/boot-bound fail-closed oturum.
- Provider process create ve Accessibility service connect/destroy/interrupt olaylarında authorization sıfırlanır ve emergency-stop güvenli duruma geçer.
- Core arm butonu Android device credential doğrulaması ister. Güven sınıfı yalnız `DEVICE_CREDENTIAL_GATED_SIGNED_CORE_SESSION`; kişisel kriptografik kimlik iddiası yoktur.
- Global action dahil action yüzeyi aktif package + signer allowlist precondition ile korunur.
- Generic launchable-app liste/inspect/onay UI; APP LABEL + PACKAGE + SIGNER SHA256 approval öncesi gösterilir.
- Onay listesi görüntüleme, tekil revoke, worker dışındaki tüm onayları reset ve default worker revoke koruması vardır.
- Secret input maskeli mod + FLAG_SECURE + action sonrası Core field clear. Accessibility snapshot password/inputType/secret metadata için `<redacted-secret>` kullanır.
- Audit iki bounded segment, sequence, previous-hash, entry-hash, process/session/boot metadata ve corruption verifier içerir. Rotation başarısızlığı fail-closed olur; privileged eylemden önce mevcut retained-chain bütünlüğü doğrulanır. Bu **retained-window iç tutarlılık/tamper-evidence** tasarımıdır; tamper-proof değildir ve ayrı anahtarla kriptografik MAC içermez.
- Action sonucu `DISPATCHED / GESTURE_COMPLETED / UI_CHANGED / TARGET_POSTCONDITION_CONFIRMED / FAILED` olarak ayrılır. UI hash değişimi hedef başarısı sayılmaz.
- Swipe/click/type/scroll/global action öncesinde fresh active-package recheck yapılır; click/type/scroll hedef node dispatch öncesinde yeniden çözülür; gesture/launch sonrası package+approval durumu tekrar kontrol edilir.
- Bridge ve Core manifestlerinde INTERNET permission yoktur; cleartext traffic kapalıdır. Bridge `QUERY_ALL_PACKAGES` istemez; yalnız Core, worker ve LAUNCHER intent görünürlüğü için `<queries>` kullanır.

## Build sözleşmesi

AGP 8.7.3, Gradle 8.9, JDK >=17, Java target 17, compile/targetSdk 35, minSdk 26, build-tools 35.0.0. Gerçek Gradle wrapper JAR zorunludur; beklenen resmî SHA-256 `498495120a03b9a6ab5d155f5de3c8f0d986a449153702fb80fc80e134484f17` değeridir. Sahte veya elle üretilmiş wrapper JAR kabul edilmez.

`SOURCE_*` testleri build değildir. `COMPILE_PASS`, `APK_STATIC_PASS`, `SIGNER_PASS`, `DEVICE_PASS`, `PHONE_ACTION_PASS`, `END_TO_END_PASS` ayrı gate'lerdir.

## Açık mimari gate

Worker çıktısını `screenRead → model/tool router → owner policy → Bridge action → postcondition` döngüsüne bağlayan AI karar/ToolBus entegrasyonu bu kaynakta henüz yoktur ve `OPEN_DEFECT` olarak kalır.
