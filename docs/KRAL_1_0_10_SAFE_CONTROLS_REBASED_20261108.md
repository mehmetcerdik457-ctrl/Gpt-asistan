# KRAL Genesis 3.0 — Güncel 1.0.10 + P0 üzerine güvenli Owner/CİHAT/Model kontrolleri

## Kaynak bağlama
- Geliştirme başlangıcı: PR #97 exact commit `8eeacf43466d2bda6a22cfbaf1fd1382c4f8982e`.
- Referans işlevler: eski PR #99 @ `7d521546ac86667d2554778e7514cd6ff5aba8d5`.
- Bu çalışma, mevcut PR #99'u rebase/merge etmez; gerekli işlevleri güncel
  1.0.10 tabanına **ayrı dosya ve seçici yama** olarak taşır.
- Aday dal: `integration/kral-1-0-10-safe-controls-rebased-20261108`.
- Hedef: `integration/kral-1-0-10-ui-preserve-20261108`, **main değil**.

## Aktarılan ve korunanlar
1. `KralIntegrationPolicy.kt` ve 7 test: owner kilidi, şifreli depolama,
   oturum meşguliyeti, CİHAT kimliği, kayıtlı sunucu için varsayılan ret.
   OMEGA/harici ayrıcalıklı yazımlar UI politikasıyla hiçbir zaman açılmaz.
2. `KralModelPorts.kt` ve 4 test: imzalı OwnerGateway'e giden yolda
   kayıtlı Owner eşleşmesi, HTTPS ve canlı doğrulanmış model kapısı. Kurulu
   olmayan yerel model runtime'ı açıkça `LOCAL_RUNTIME_NOT_CONFIGURED`
   diye reddedilir; sahte çalışan yerel LLM gösterilmez.
3. `ChatSession.kt` varsayılan yanıt sağlayıcısı doğrulanan model portuna
   yönlendirilmiştir. Önceki idempotent gönderim kayıtları, şifreli sohbet
   geçmişi, retry sınırları, oturum durumu ve yaşam döngüsü korunur.
4. `MainActivity.kt` güncel sürüm **korunarak** sadece Görevler sayfasına
   izinli CİHAT kimlik görüntüleme/onaylı açma, Owner/Bridge ve imzalı salt
   okunur worker okuması, OMEGA yazma devre dışı gösterimi ve Sohbet
   mesaj kutusuna yalnız taslak oluşturan `Ses` düğmesi eklenir.
5. 9 Türkçe string kaynağı eklendi. Mevcut Owner OTP, SQLCipher,
   `BackupUi`, `LocalTaskReminders`, gerçek ses tanıma izin isteği,
   UI task-result yönlendirmesi ve P0 read-only APK envanter koduna dokunulmaz.

## Riskler ve release kapıları
- `KralIntegrationPolicy` sadece kullanıcı arayüzündeki ek bir
  fail-closed karardır; uzak sunucu yetkilendirmesi değildir.
  OwnerGateway imza, nonce, idempotency ve server owner validation
  zorunlulukları aynen devam eder.
- CİHAT uygulamasının gerçekten güvenilir/üreticiye ait olduğu kimlik
  denetimini geçmedikçe açılmaz. Kullanıcı onayı olmadan pano, sohbet,
  dinleme veya üçüncü taraf uygulama kontrolü yapılmaz.
- OMEGA için canlı dosya/hesap yazımı etkinleştirilmez.
- Canlı OpenAI/SMTP/yerel LLM burada çalıştırılmadı; yalnız port ve UI
  davranışları test edilebilir.
- Yeni tam HEAD için Python/Kotlin JVM/lint/API30/API36/şifreli backup-copy
  CI sonuçları **ayrı doğrulanmadan** eski PR #97/#99 başarıları kabul edilmez.
- Mevcut APK'nın fiziksel cihazda imzası ve yerinde veri koruyan güncelleme
  doğrulanmadan APK kurulumu veya Play yayını yapılmaz.
- Production keystore/secret/OAuth, main, orijinal APK, önceki Drive
  delilleri ve kullanıcının Android verileri değiştirilmez.

Bu belge varsayılan salt-okunur/dry-run ve bağımsız code review kapısını
korur. Birleştirme ancak ayrıca sağlanan owner onayı ve ilgili kaynak-bağlı
delillerle değerlendirilebilir.
