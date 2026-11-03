# KRAL Genesis Android teslim denetimi — 3 Kasım 2026

## Kaynak ve koruma

Ana dal: `5062b22ccfc11bdd10302bed75e5902deeb4ea4c`.
Çalışma tabanı: `057606ccfe3c5d1530022842b1901bd60a00367f`,
`integration/kral-genesis-task-runtime-20261103` (PR #85).
Bu teslim ayrı `fix/kral-genesis-android-delivery-20261103` dalındadır.
Mevcut dosyalar korunur; main'e merge, üretim dağıtımı ve secret değişikliği yapılmaz.

## Gerçek düzeltmeler

- `78ad917c81e7308e4162b934e60599efe0f367bb` dalındaki mevcut CihatHandoff,
  CihatIdentity ve SpeechDraft kodları ile testleri geri alınır. Güncel
  şifreli depolama, sahip kapısı ve görev orkestratörü değiştirilmeden bağlanır.
- Ses tanıma kullanıcı onayıyla harici Android hizmetini açar; dönüş yalnız
  taslağa eklenir, yeniden cihaz doğrulaması gerekir. RECORD_AUDIO veya yeni
  Android çalışma izni eklenmez. Türkçe TTS mevcut kodda korunur.
- CİHAT geçişi yalnız tarihsel 3.2.1 (893) imza/sürüm pini eşleşirse ve kullanıcı
  seçerse çalışır. Bu pinin taşınması canlı CİHAT backend doğrulaması değildir.
  Pano aktarımı önizlemeli ve kullanıcı seçimine bağlıdır; otomatik mesaj yoktur.
- 12 uzman rolü için mevcut çift P-256 imzalı task API arayüze bağlanır.
  Oluşturma, elle durum okuma, iptal ve iki salt okunur sunucu işçisi kullanılabilir.
  İstek/yanıt hash'leri ve görev kimlikleri doğrulanır; sonuç şifreli geçmişe yazılır.
  Taslak korunur. Model önerileri araç veya sistem komutuna çevrilmez.
- İptal edilen bir görevin ortak çalışma slotunu bekledikten sonra sağlayıcıya
  gitmesi engellenir. Başlamış senkron HTTP isteği uzaktan kesilmez; sonucu bastırılır.
- APK sürümü `1.0.4-genesis-candidate`, versionCode `5` olur.
- CI gerçek JUnit XML sonuçlarından başarılı/atlanan testleri ayrı sayar,
  Lint XML hatalarını reddeder; APK ile SHA-256, tam commit, SDK/Gradle/Java
  sürümleri ve sonuç özeti aynı Actions artefaktına konur.
- Kaynak ve APK içeriğinde tanınabilir kimlik bilgisi kalıpları çevrimdışı taranır.
  Rapor sır değerlerini yazmaz. Kalıp taraması her tür sırrın yokluğunu ispatlamaz.

## Android Studio / GitHub Actions

Bu mevcut Gradle projesidir. Android Studio kök dizinden açabilir.
JDK 17; Gradle Wrapper 8.13 (SHA-256 sabitli); AGP 8.13.2; Kotlin 2.3.21;
compile/target SDK 36; min SDK 26; SQLCipher Android 4.19.1; AndroidX SQLite 2.7.0.
Actions SDK platform 36 ve build-tools 36.0.0'ı açıkça kurar.

Actions komutu:

```sh
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest :app:bundleRelease --no-daemon --stacktrace
```

Aynı APK API 30/36 emülatörlerine kurulur, Android instrumentation,
şifreli veritabanı ve sahip kilidi testleri çalıştırılır. Gerçek test sayıları
`test-summary.json`, `instrumentation-summary.json` ve ham loglardadır.
Bu belge henüz çalışmamış yeni commit için başarı sayısı iddia etmez.

Yerel Java 17 doğrulandı. Yerel Gradle indirme denemesi ağ erişimi nedeniyle
başlamadı; Android derleme/test kanıtının kaynağı bu commit'in Actions çalışmasıdır.

## Mevcut entegrasyon dallarının karşılaştırması

Aşağıdaki envanter bütün 28 güncel `integration/` ref'ini yapısal olarak karşılaştırır.
Ayrılan commit sayısı `dal / çalışma tabanı`; ek dosyalar `app/server/scripts`
altında bu tabanda bulunmayan yollardır. Bu sayılar modülün çalıştığını veya
her ayrık dalın bu teslimde birleştirildiğini göstermez. Eski dal kaynakları korunur.

| Dal | HEAD | Ayrılan commit | Taban dışında dosya |
| --- | --- | ---: | ---: |
| `integration/cihat-github-task-bridge-20261021` | `f252d2499d39` | 63 / 86 | 21 |
| `integration/genesis8-copilot-20261024` | `320bd7a662ff` | 69 / 86 | 21 |
| `integration/kral-50-worker-supervisor-20261025` | `92284d7a15f6` | 85 / 86 | 30 |
| `integration/kral-asistan-20261020` | `c5ff163227ac` | 0 / 79 | 0 |
| `integration/kral-cihat-voice-unified-20261022` | `78ad917c81e7` | 51 / 86 | 21 |
| `integration/kral-cloud-fifty-slot-20261028` | `49cc40916c5a` | 96 / 86 | 38 |
| `integration/kral-durable-chat-20261020` | `79997f009856` | 0 / 87 | 0 |
| `integration/kral-eight-runner-proof-20261027` | `d5ea92fe31e8` | 88 / 86 | 32 |
| `integration/kral-genesis-android-source-ui-20261024` | `f4eaba2f713e` | 81 / 86 | 42 |
| `integration/kral-genesis-apk-static-evidence-20261024` | `ec825dba87a0` | 76 / 86 | 37 |
| `integration/kral-genesis-local-document-audit-20261025` | `50b741248a79` | 108 / 86 | 52 |
| `integration/kral-genesis-owner-source-api-20261024` | `2762f685bb2f` | 79 / 86 | 40 |
| `integration/kral-genesis-owner-source-dirfd-hardening-20261024` | `fac39b87afbd` | 85 / 86 | 43 |
| `integration/kral-genesis-resource-discovery-20261024` | `694b28617c37` | 75 / 86 | 35 |
| `integration/kral-genesis-source-picker-20261024` | `1bbe8f55d67a` | 96 / 86 | 46 |
| `integration/kral-genesis-task-runtime-20261103` | `057606ccfe3c` | 0 / 0 | 0 |
| `integration/kral-legacy-agents-recovery-20261025` | `98805e746ced` | 80 / 86 | 23 |
| `integration/kral-local-db-encryption-20261021` | `c1b5d63954df` | 9 / 86 | 3 |
| `integration/kral-offline-autonomy-20261101` | `4ba77b621177` | 16 / 82 | 0 |
| `integration/kral-openai-privacy-case-evidence-20261027` | `c868a966f848` | 3 / 91 | 0 |
| `integration/kral-pr39-exact-head-apk-proof-20261023` | `5a98a4fa45a6` | 76 / 86 | 35 |
| `integration/kral-pr50-real-apk-signed-ci-20261024` | `b61ee57d09cd` | 84 / 86 | 43 |
| `integration/kral-secret-readiness-20261028` | `a9b5791aa7bc` | 98 / 86 | 38 |
| `integration/kral-sol-wal-idempotency-workers-20261101` | `5bc10c49d2a1` | 11 / 81 | 0 |
| `integration/kral-termux-local-proof-20261028` | `43216650efe4` | 91 / 86 | 34 |
| `integration/kral-verify-continuation-20261027` | `3206a5a8aabf` | 2 / 82 | 1 |
| `integration/kral-voice-draft-20261022` | `b62b41e70646` | 1 / 85 | 2 |
| `integration/owner-omega-v1-signer-20261020` | `639ac11db15e` | 188 / 91 | 41 |

## Kabul sınırları

- Yerel hafıza ve görevler cihazın ayrı SQLCipher veritabanındadır; Termux verileri
  kendiliğinden aktarılmaz ve eski kaynaklar silinmez.
- Sunucu kaydı, kullanıcının yönettiği HTTPS adresi ve sunucu ortamındaki sağlayıcı
  anahtarı gerekir. APK sağlayıcı anahtarı içermez. Bu çalışmada canlı veya ücretli
  model çağrısı, hesap/OAuth/anahtar oluşturma yapılmaz.
- 50 mantıksal slot ve en fazla 4 eşzamanlı sunucu model isteği mevcut backend
  sınırıdır; 50 dış model veya sürekli çalışan ajan iddiası değildir.
- Android uygulamasında farklı uzman görevleri gönderilebilir; önerilerin dış
  sistemde uygulanması bu arayüzden yetkilendirilmez.
- Aday APK debug imzalıdır. Önceden kurulu APK ile imza uyumu ve telefon üzerinde
  yükseltme doğrulanmadı. İmza uyuşmazlığında veri silme veya kaldırma önerilmez.
  Release AAB imzasızdır, Play Store'a hazır sayılmaz.
- Fiziksel telefon, gerçek biyometri, mikrofon/hoparlör, yüklü üçüncü taraf CİHAT
  ve canlı model hesabı bu CI koşusuyla test edilmiş sayılmaz.
