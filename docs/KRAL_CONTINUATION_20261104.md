# KRAL 1.0.9 devam çalışması

Bu devam, test edilmiş `345f8c0e2c0f1c7438a2ee0dffedcade0d67c693`
kaynağından ilerler; mevcut PR #92 güncellenir. Önceki APK ve kaynak geçmişi
korunur. Ana dalın zorunlu bağımsız inceleme kuralı değiştirilmez.

## Düzeltilen gerçek hatalar

- Model yenileme, dört yerel işçi slotunu beklerken kayıt kilidini tutuyordu.
  Slot bekleme ve sağlayıcı çağrıları kilit dışında yapılır; eski yenileme
  sonuçları yeni yapılandırmayı ezemez. Eski kodda hata veren üç eşzamanlılık
  regresyonu yeni kodda geçer.
- Hafıza hazırlığı hatası idempotency isteğini kalıcı işleniyor durumunda
  bırakabiliyordu. Sağlayıcıya hiç gidilmemiş hatalar serbest bırakılır.
  Sağlayıcı çağrısı denenmiş belirsiz sonuçlar tekrar POST edilmez.
- Sağlayıcı hatasının code/request-id alanlarında anahtar yansıması engellenir.
  Anahtarı içeren başarılı yanıt alanları da dışarı verilmez. Denemeler yalnız
  sentetik sırlar ve izole upstream ile yapılır.
- Android özel diyalogları ayrıca FLAG_SECURE taşır.
- Görev başlangıcı, executor zamanlaması ve terminal durumun SQLite kaydı
  sırasında oluşan geçici hatalar artık görevleri sessizce kuyrukta bırakmaz.
  Sınırlı yeniden denemeler yalnız veritabanına yazmayı tekrarlar; sağlayıcı
  POST'u tekrarlanmaz. Depolama düzelince bekleyen terminal kayıtlar tamamlanır.
  Sağlayıcı yanıtından sonraki kayıt hatasında bilinen yanıt/istek kimlikleri
  korunur. İstemciye verilecek kabul kaydı işçi başlamadan hazırlanır.
  Executor kuyruğa ekledikten sonra hata verse bile kabul kapısı sağlayıcı
  çağrısını önler; bütün çıkışlarda bekleyen işçi serbest bırakılır.

## Hafıza silme

Son inceleme düzeltmeleri: Android dosya seçici bekleyen işleminin türü
ekran yeniden oluşturulurken korunur; dönüşte yeniden cihaz doğrulaması ve
gerekirse yerel ekran/depo kurulumu yapılır. Parola ve dosya URI'si kayıt
durumuna yazılmaz. Kimlik doğrulama ekranında süreç yenilenirse geçersiz/eski
sonuç erişim açmaz; kullanıcıya yeniden başlatma bildirimi verilir. Kilitli
ekranlar art arda yeniden oluşturulduğunda mevcut taslak da korunur.

Hafıza, hatırlama ve görev listelemeleri toplam 30.000 karakterlik görüntüleme
bütçesine uyar; Unicode çiftleri kesilmez ve kısaltma açıkça belirtilir.
Asıl kayıtlar değişmez; 32.000 karakterlik ledger güvenlik sınırı korunur.

Sohbet ve model doğrulama, dolu yürütme kapasitesinde ücretli istek
başlatmadan hızlıca reddedilir. Hazırlık için sunucu içi süre bütçesi,
model doğrulamada sınırlı iki probe dalgası vardır; otomatik tekrar yoktur.
Android aynı gönderimin korelasyon UUID'sini idempotency anahtarı olarak da
gönderir; yeni gönderim yeni anahtar alır.

Geri yükleme artık hedefte ana/TEMP trigger varsa başlamaz. Eklemeden sonra
bütün mantıksal kayıtlar çözülmüş yedekle karşılaştırılmadan commit yapılmaz;
sessizce satır atlayan veya değiştiren hedef kurallarında bütün işlem geri alınır.

Hafıza menüsündeki tek kayıt silme akışı, kayıt seçimi sonrasında yeniden
cihaz doğrulaması ve açık onay ister. ID, zaman ve metin birlikte eşleşmeden
kayıt silinmez; aynı ID sonradan kullanılsa bile eski seçim yeni kaydı silemez.
Diğer notlar, sohbet ve görevler korunur. Bu işlem sohbetlerdeki veya eski
yedeklerdeki kopyalar için adli güvenli silme iddiası değildir.

## Kullanıcının seçtiği şifreli yedek

Hafıza → Şifreli yedek / geri yükleme menüsü Android dosya seçicisini açar.
Dosya dönüşünde cihaz doğrulaması yeniden gerekir. Parola en az 12 karakterdir;
oluştururken iki kez yazılır. Parola Activity durumuna kaydedilmez, otomatik
doldurma kapalıdır ve diyalog kapanınca alanlar temizlenir.

Kayıtlar AES-256-GCM ile şifrelenir; her dosyada rastgele salt ve nonce,
PBKDF2-HMAC-SHA256 için sabit 310.000 yineleme kullanılır. Başlık da doğrulanır.
Dosya, satır sayısı ve alan boyutları sınırlıdır. Düz metin geçici dosya veya
cihaz/sahip anahtarı dışa aktarılmaz. Yedek yalnız hafıza, görev ve sohbet içerir;
model ayarları, uzak sunucu görevleri ve sahip anahtarları dahil değildir.

Geri yükleme tamamen çözülüp doğrulanmadan hedef veritabanı açılmaz. Hedefin
uygulama tabloları boş olmalıdır; kayıtlar tek SQL transaction içinde eklenir.
Yanlış parola, değişmiş dosya, dolu hedef ve kısmi ekleme hatası mevcut veriyi
değiştirmez. Geçerli Android locale metaverisi korunur. Ayrı anahtarlı SQLCipher
test depolarında geri yükleme ve yeniden açma testleri eklenmiştir; bunlar
fiziksel ikinci telefon kurulumu iddiası değildir.

CI ayrıca yeni açılmış API 30 emülatöründe gerçek kurulum döngüsünü sınar:
başlangıçta iki test paketinin de bulunmadığını doğrular, yalnız kendisinin
kurduğu debug paketlerinde sentetik kayıt oluşturup şifreli yedeği çıkarır;
bu test kurulumunu kaldırıp aynı APK'ları yeniden kurar. Yeni kurulumda eski
veritabanı, anahtar tercihi ve Android Keystore takma adı bulunmadan yedek
geri yüklenir. Şifreli dosyanın hash'i ve geri yüklenen kayıtlar doğrulanır.
Bu akış normal testlerden ayrı çalışır ve yayın kapısına dahildir. Fiziksel
telefonlara veya önceden mevcut kurulumlara uygulanamaz.

## Tekrarlanabilir bağımsız kontroller

`scripts/acceptance/run_exact_source_audit.py <tam-commit>` istenen Git kaynağını
izole arşivden çalıştırır. Gerçek yerel HTTP/P-256/SQLite süreç yeniden başlatma,
işlem tekrarı, eski bot ve injection denemeleri ile sentetik sır yansıtma
kontrolleri CI içinde sürekli çalışır. Canlı veya ücretli sağlayıcı çağrısı yoktur.

Bu dosya yeni commit'in henüz tamamlanmamış Android CI sonucu için PASS iddia
etmez. Sonuçlar exact commit'in Actions artefaktlarından okunmalıdır.
