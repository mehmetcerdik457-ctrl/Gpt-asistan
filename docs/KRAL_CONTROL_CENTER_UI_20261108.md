# KRAL Genesis 3.0 — Android kontrol merkezi (8 Kasım 2026)

## Kaynak zinciri ve sınırlar

- Kaynak: PR #86, `fix/kral-genesis-android-delivery-20261103`,
  tam commit `5c365322ca1722d0e837a2785d4fc4401cea56b8`.
- Bu çalışma: `feature/kral-control-tabs-20261108`, PR #86 üstüne
  eklenen ayrı inceleme dalıdır.
- `main` değiştirilmedi; mevcut şifreli veri şeması, kimlik/imza
  sistemi, işçi yürütme izinleri, API sözleşmeleri ve manifest korunur.
- Kaynakların varlığı canlı OpenAI, CİHAT veya OMEGA erişimi kanıtlamaz.
  Bu çalışma sadece kullanıcı arayüzünü gruplar.

## Uygulanan değişiklik

- `KralControlSections.kt`: üç sekme, görünürlük yönetimi ve 48dp
  asgari dokunma yüksekliği. Sekme değiştirmek dış sistem eylemi yapmaz.
- `MainActivity.kt`: mevcut eylemler aynen korunarak Sohbet (sohbet,
  taslak, ses/CİHAT), Görevler (yerel hafıza/görev, uzman görevleri)
  ve Sistem (model, Owner/Bridge, sunucu bilgisi, TTS) sekmelerine yerleşir.
- Bağlantı durumu tüm sekmelerin üstünde görünür kalır.
- Görevlerden hafıza/yerel görev raporu açılınca sohbet geçmişine
  geçilir; yeni görev sonucu geldiğinde sohbet bölümü görülebilir.
- OMEGA için durum metni canlı bağlantı olmadığını açıkça belirtir.
- Türkçe ekran metinleri `strings.xml` dosyasındadır.

## Risk ve kontrol matrisi

| Kontrol | Bu değişiklik | Kabul kanıtı |
| --- | --- | --- |
| Owner kilidi | Değişmez | API 30/36 kilit ekranı instrumentation |
| SQLCipher / sohbet geçmişi | Şema değişmez | Yerel veritabanı ve taslak saklama testleri |
| CİHAT | Kullanıcı onaylı geçiş korunur | Mevcut CihatHandoff ve imza testleri |
| Uzman görevleri | Sadece mevcut bağlı eylem menüsü | OwnerGateway ve ExpertTasks testleri |
| Model bağlantısı | Yeni anahtar veya sağlayıcı yok | Gateway testleri; canlı model ayrı kapı |
| AAB / APK | Geliştirme artefaktı; Play yayını yok | SHA-256 + imza + aynı commit kanıtı |

## Bağımsız kabul kapıları

1. `./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest :app:bundleRelease --no-daemon --stacktrace`
2. `python -m unittest discover -s server/tests -v`
3. GitHub Actions aynı yeni HEAD commit için başarılı ve ilgili kanıtlar
   mevcut olmalı; geçmiş PR #86 sonuçları yeni HEAD sonucu yerine geçmez.
4. Android API 30 ve 36 emülatörlerinde sahibin kilit ekranı, üç sekme,
   taslağı koruma, giriş/geri dönüş ve hata durumları incelenmeli.
5. Önceki APK üzerine veri kayıpsız yükseltme; imza sertifikası;
   fiziksel telefon, canlı model ve Play yayın testleri **ayrı** engellerdir.
   Bunlar bitmeden "production-ready" denmez.

## Sonraki kontrollü geliştirme

- Model sağlayıcı katmanı: mevcut çift imzalı OwnerGateway ve sunucudaki
  Responses API korunarak yerel LLM için **ayrı, doğrulanmış** adaptör.
- OMEGA görev paneli: önce salt okunur durum; sonrasında belirli bir
  işlem için ayrı sahip onayı, idempotency, audit ve geri alma.
- CİHAT: otomatik sohbet okuma veya özel uygulama denetimi eklenmez;
  kullanıcı aracılı geçiş mevcut güvenlik sınırıdır.
- Sıfırdan yeni uygulama, depolama sıfırlama, release imzası değiştirme
  veya main'e merge bu çalışmanın kapsamı dışındadır.
