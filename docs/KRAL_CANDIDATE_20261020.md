# Kral Asistan: kalıcı sohbet ve doğrulanabilir debug adayı

Bu değişiklik mevcut integration/kral-asistan-20261020 kaynağını temel alır; uygulama veya eski Owner/Bridge bileşenleri yeniden yazılmamıştır.

Sohbet artık kral_local.db içinde saklanır. V1 hafıza ve görev tabloları korunarak V2 chat_messages tablosu eklenir. Ekranda son 200 kayıt gösterilir; daha eski veriler bu sınır nedeniyle silinmez. Yerel komutun değişikliği ve sohbet kaydı aynı veritabanı işlemiyle yazılır.

Bekleyen model isteği Activity yerine AndroidViewModel tarafından yönetilir. Ekran yeniden oluşturulsa da istek ve kayıt işi devam eder; aynı oturumda ikinci eşzamanlı gönderim kabul edilmez. Gönderim kaydedilmeden giriş alanı temizlenmez; taslak ekran yeniden oluşturulurken korunur. Bu, işletim sisteminin uygulama sürecini zorla öldürmesinden sonra ağ isteğinin devam edeceği anlamına gelmez.

Türkçe TTS desteği kontrol edilir; kullanıcı yanıtları seslendirmeyi açabilir. TTS motoru görünürlüğü Android queries içinde tanımlıdır. Gerçek ses çıktısı cihaz testi gerektirir.

Model taşıyıcısı HTTPS, JSON ve UTF-8 kontrolü yapar; okuma sırasında 128 KiB sınırı uygular. Yönlendirme izlemez. HTTP/JSON/ağ hatası başarılı model yanıtı sayılmaz. URL içinde kullanıcı bilgisi, sorgu ve parça kabul edilmez. Sağlayıcı anahtarı eklenmemiştir. Sunucuya yalnız güncel soru gönderilir; geçmiş, hafıza ve görevler otomatik gönderilmez.

Debug paket adı com.example.gptasistan.candidate, sürüm 1.0.2-kral-candidate (3). Bu, mevcut com.example.gptasistan uygulamasına güncelleme değildir. Yerel debug sertifikası kalıcı yayın/güncelleme imzası sayılmaz.
Android uygulama alanları ayrıdır; eski uygulamanın gerçek kişisel verileri bu adaya otomatik içe aktarılmaz. V1→V2 geçiş testi aynı uygulama veritabanının şema yükseltmesini doğrular.

Doğrulama komutu:

```sh
gradle :app:testDebugUnitTest :app:assembleDebug :app:lintDebug --no-daemon
```

Robolectric/JVM ve sahte HTTP bağlantısı testleri fiziksel telefon veya canlı AI testi değildir. Mevcut güvenli kullanıcı oturumu, gerçek model erişimi, birden fazla doğrulanmış model seçimi, mikrofon girişi, Owner/Bridge işlemleri, şifreli hafıza/yedek ve biyometrik kullanıcı kabulü bu adayda tamamlandı sayılmaz. Model adresi kaydetmek bağlantıyı doğrulamaz.

Kaynak depo test altyapısı için JVM test bağımlılıklarını içerir; üretim APK'sına Robolectric ve JVM org.json test kitaplığı paketlenmez. Kasa, credential, debug keystore ve makineye özel SDK/Gradle önbellekleri teslim kaynaklarına katılmamalıdır.
