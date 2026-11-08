# KRAL Genesis 3.0 / 1.0.10 — güvenli kontroller kabul kaydı

## Kaynak, dal ve entegrasyon kuralı

- Taban: PR #97 `integration/kral-1-0-10-ui-preserve-20261108`, commit
  `6f9a7e125b585ff697f74ebeddb191d1a6fa170a`.
- Kaynak: PR #95'teki güvenli model portu ve CİHAT/OMEGA görünür kontrollerinin
  1.0.10 uyarlaması. 1.0.6 `MainActivity.kt` dosyası kopyalanmaz.
- Bu katman 1.0.10 mevcut OTP, şifreli yedek/geri yükleme, hatırlatıcı,
  hafıza silme onayı, SQLCipher, idempotent görev gönderimi, Owner kilidi ve
  tüm orijinal Android izinlerini korur.
- `main` merge, release imzası, uygulama kurulum/veri sıfırlama veya Play
  yayını bu çalışmanın dışında tutulur.

## Kod değişiklikleri

1. `KralIntegrationPolicy`: Owner kilidi, şifreli depolama, oturum meşguliyeti,
   CİHAT statik kimliği ve kayıtlı sunucu için varsayılan reddetme.
   Ayrıcalıklı dış dosya/hesap yazımı daima reddedilir.
2. `MainActivity` Görevler sekmesine CİHAT doğrulama, kullanıcı onaylı uygulama
   açma, Owner/Bridge yerel durumu, imzalı salt okunur işçi durumu, devre dışı
   OMEGA dış işlem denetimi ve açıklama metni eklenir.
3. Sohbet mesaj kutusunda `Ses` düğmesi: Android speech recognizer için
   kullanıcı diyalogu açar; sonuç yalnız taslağa yazılır. Otomatik mesaj
   gönderimi, gizli panoya aktarım veya konuşma kaydı yoktur.
4. `SignedOwnerModelPort` yalnız halihazırdaki `OwnerGateway` sunucu
   yolunu kullanır; sahip eşleşmesi ve canlı doğrulanmış model kaydı
   olmadan yanıt üretemez. `UnavailableLocalModelPort` kurulu olmayan
   yerel LLM için kesin ret verir, sağlayıcı anahtarını saklamaz.
5. `ChatSession` varsayılan yanıt yolu bu port üzerinden geçer; 1.0.10
   idempotency alanları ve uzman görev yeniden gönderim yolu değişmez.

## Test ve kanıt sınırı

- Yeni Kotlin testleri: `KralIntegrationPolicyTest.kt` (7 temel izin testi),
  `KralModelPortsTest.kt` (4 model bağlantısı ret testi).
- PR #97 CI sonuçları yeni dalın kanıtı değildir. Kabul için bu yeni PR'ın
  kendi HEAD SHA'sında Python, JVM, Android lint, 30/36 emulator, APK/AAB
  kaynak/hash kanıtlarını ayrı oku.
- Başarılı emülatör açılışı = kilit ekranı görünürlüğü; gerçek kullanıcı
  kimliği, fiziksel cihaz ve canlı sağlayıcı kabulü değildir.
- 1.0.10 release imzası, eski kurulu APK sertifikasıyla uyum ve veri koruyan
  kurulum yükseltmesi **BLOCKED** kalır.
- OMEGA canlı bağlantısı ve CİHAT otomatik mesaj API'si bu kodda açılmaz.
- Google Drive'a, eklentiye veya başka harici servise özel kaynak kodu,
  kimlik anahtarı, OTP, şifre, kişisel sohbet kaydı aktarılmaz.

## Hedef kabul

PR inceleme ve aynı HEAD'de CI başarıları tamamlandıktan sonra dahi PR
taslak kalır. Fiziksel cihaz/Owner sign/kurulu uygulama sertifikası/yedek
geri yükleme ve canlı model kabulü için ayrı kanıt gerekir.
