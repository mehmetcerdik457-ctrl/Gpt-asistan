# Yerel veritabanı şifrelemesi

KralStore, kullanıcı sohbeti, hafıza ve görev tablolarını SQLCipher Community Edition 4.19.1 ile şifreli SQLite dosyasında saklar. SQLCipher yerel Android kütüphanesi ilk veritabanı işleminden önce yüklenir. Veritabanı için ilk kurulumda 32 bayt kriptografik rastgele bir passphrase üretilir; anahtar, dışa aktarılamayan Android Keystore AES-256/GCM anahtarıyla sarılır. Uygulama ayarlarında yalnız IV ve GCM ciphertext tutulur. Keystore anahtarı ya da sarılmış passphrase kayıpsa uygulama yeni anahtar üretip mevcut verinin üzerine yazmaz; veritabanı açılışı hata verir ve dosya korunur.

İlk açılışta sürüm 1 veya 2 plaintext `kral_local.db` tespit edilirse kaynak salt okunur anlamda korunarak SQLCipher staging dosyasına `sqlcipher_export` ile kopyalanır. Kaynak şema, kullanıcı sürümü, gerekli tablolar ve SQLCipher `quick_check` doğrulanır. Sürüm 1 için sohbet tablosu eklenir. Ancak staging dosyası şifreli olarak yeniden açılıp doğrulandıktan sonra atomik adlandırma ile etkin dosya yapılır; doğrulama başarısızsa geri alma denenir ve plaintext kaynak tutulur. Başarılı geçişten sonra eski plaintext dosyası silinir. Flash depolamada eski blokların fiziksel olarak geri getirilemeyeceği garanti edilemez.

Bu tasarım yalnız cihazdaki mevcut veritabanının bekleyen/veri-at-rest içeriğini korur; canlı sunucu kimlik doğrulaması, kullanıcı kilit ekranı yetkilendirmesi, yedekleme, cihazlar arası aktarım veya kurtarılabilir şifreli yedek sağlamaz. Uygulamanın mevcut Android yedekleme kuralları DB ve ayarları dışlar; cihaz/veri kaybında bu yerel veriler kurtarılamaz. Böylece yedeğe anahtar sızdırılmaması sağlanır, fakat yedek/kurtarma gereksinimi ayrı bir aşama olarak kalır.

## Bağımlılık ve kaynaklar

- `net.zetetic:sqlcipher-android:4.19.1@aar` — SQLCipher for Android Community Edition, Android API 23+; kaynak README ve sürüm: <https://github.com/sqlcipher/sqlcipher-android>
- `androidx.sqlite:sqlite:2.7.0` — SQLCipher Android binding ile birlikte kullanılan SQLite API.
- SQLCipher Community Edition MIT-benzeri BSD lisansı: <https://github.com/sqlcipher/sqlcipher-android/blob/master/LICENSE>
- SQLCipher anahtar yönetimi ve Keystore yaklaşımı: <https://www.zetetic.net/sqlcipher/database-key-material/>
- SQLCipher plaintext veritabanı export ve `sqlcipher_export`: <https://www.zetetic.net/sqlcipher/sqlcipher-api/>
- Android AES/GCM önerisi: <https://developer.android.com/privacy-and-security/cryptography>
- Android Keystore anahtarlarını dışa aktarmaya karşı koruma: <https://developer.android.com/privacy-and-security/keystore>
- Android backup/extraction rule davranışı: <https://developer.android.com/identity/data/autobackup>

## Lisans bildirimi

SQLCipher Android üçüncü taraf lisans metni `THIRD_PARTY_LICENSES.md` içindedir. Kütüphane Android Community Edition'ı kullanılır; bu projede ticari/enterprise lisans veya anahtar yoktur.
