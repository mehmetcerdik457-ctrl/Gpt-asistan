# ORBA çalışma zamanı yapılandırması

`server.play_runtime.build_play_runtime()` doğrulanmış sunucu yapılandırmasından
`PlayRuntime(play_boundary, rtdn_processor)` oluşturur. İki bileşen de varsayılan
olarak `None` döner. Oluşturma işlemi PostgreSQL'e bağlanmaz, ADC okumaz,
Google'a istek göndermez, tablo oluşturmaz ve HTTP dinleyicisi açmaz.

`ORBA_PLAY_BOUNDARY_ENABLED`, `ORBA_PLAY_RTDN_ENABLED` ve
`ORBA_PLAY_OAUTH_ENABLED` için yalnız `YES` ve `NO` kabul edilir; eksik değer
`NO` anlamına gelir. En az bir uç nokta açılacaksa OAuth da açık olmalıdır.
Eksik veya hatalı yapılandırma, gizli değer içermeyen
`RuntimeConfigurationError` ile açılışı reddeder. Bayraklar tek başına bir
bileşen oluşturmaz.

## Ortak zorunlu alanlar

| Değişken | Kural |
| --- | --- |
| `ORBA_PLAY_DATABASE_DSN` | Açık PostgreSQL host, kullanıcı ve veritabanı; loopback dışı adreslerde sunucu kimliğini doğrulayan açık `sslmode=verify-full` zorunludur. `require` ve `verify-ca` yeterli değildir. |
| `ORBA_PLAY_DATABASE_SCHEMA` | İsteğe bağlı; varsayılan `orba`. Küçük harf/rakam/alt çizgi; ilk karakter harf, en çok 63 karakter. Sistem şemaları reddedilir. |
| `ORBA_PLAY_PUBLISHER_SERVICE_ACCOUNT` | ADC'nin temsil etmesi gereken tam Google servis hesabı e-posta adresi. |
| `ORBA_PLAY_PRODUCTS` | Virgülle ayrılmış benzersiz ürün kimlikleri; boşluk, boş öğe veya yinelenen kimlik kabul edilmez. |
| `ORBA_PLAY_PACKAGE` | `server.play_entitlement_gate.PACKAGE` ile birebir aynı Android paket kimliği. |
| `ORBA_PLAY_SERVER_SECRET_B64` | En az 32, en çok 4096 baytlık sunucu sırrının kanonik URL-safe Base64 kodlaması. Sır dağıtım sırasında gizli yapılandırma üzerinden sağlanır. |

DSN'de servis dosyası, birden fazla host, `hostaddr` ve başlangıç `options`
parametreleri kabul edilmez. Bağlantılar istek sırasında, `autocommit=True`
ve 5 saniyelik bağlantı zaman aşımıyla açılır. Şema güvenilir yönetici
tarafından ayrıca kurulmalıdır; çalışma zamanı otomatik migration yapmaz.

libpq'nin DSN dışından hedef seçmesini önlemek için `PGHOSTADDR`, `PGSERVICE`,
`PGSERVICEFILE`, `PGSYSCONFDIR`, `PGOPTIONS`, `PGHOST`, `PGPORT`, `PGDATABASE`,
`PGUSER` ve `PGSSLMODE` hem verilen yapılandırmada hem gerçek süreç ortamında
reddedilir. Denetim açılışta ve her bağlantı öncesinde tekrarlanır. Hata yalnız
alan adını bildirir. `PGPASSWORD`, `PGPASSFILE` ve `PGSSLROOTCERT` kimlik
bilgisi/TLS kaynakları olarak kullanılabilir; değerleri raporlanmaz.

Her iki bileşen etkinse satın alma doğrulaması ve RTDN aynı
`PostgresPlayStore` nesnesini, aynı şemayı, aynı ürün listesini ve aynı OAuth
sağlayıcısını kullanır. RTDN snapshot yazıcısı da bu şemaya sabitlenir.

## Satın alma doğrulama sınırı

`ORBA_PLAY_BOUNDARY_ENABLED=YES` ek olarak mevcut çift P-256 sahibi
yapılandırmasını gerektirir:

- `OMEGA_OWNER_ID`
- `OMEGA_DEVICE_ID`
- `OMEGA_OWNER_PUBLIC_DER_B64`
- `OMEGA_DEVICE_PUBLIC_DER_B64`
- `OMEGA_NONCE_DB`

İki public key geçerli, kanonik DER biçiminde, farklı P-256 anahtarları
olmalıdır. Cihaz kimliği, cihaz anahtarının DER baytlarının SHA-256 özetiyle
eşleşmelidir. Nonce veritabanı yolu mutlak olmalı ve üst dizini önceden
bulunmalıdır; oluşturucu hiçbir anahtar veya dosya üretmez. Public key
yapılandırmasını sahipliği ayrıca doğrulanmış Android kayıt çıktısından
alın. Bu denetim tek başına gerçek kişi sahipliğini kanıtlamaz.

## RTDN

`ORBA_PLAY_RTDN_ENABLED=YES` şu alanları da gerektirir:

- `ORBA_PLAY_PUBSUB_AUDIENCE`: query, fragment veya kullanıcı bilgisi
  içermeyen tam HTTPS webhook adresi.
- `ORBA_PLAY_PUBSUB_SERVICE_ACCOUNT`: imzalı Pub/Sub OIDC belirtecinde
  beklenen servis hesabı.
- `ORBA_PLAY_PUBSUB_SUBSCRIPTION`: tam
  `projects/<proje>/subscriptions/<abonelik>` adı.

Yalnız RTDN etkinse P-256 sahibi anahtarları gerekmez. Bildirimler Google
OIDC ile doğrulanır; abonelik durumu ayrıca Play API üzerinden tekrar
okunur. Snapshot veya HTTP 200 yanıtı tek başına ücretli erişim vermez.

## ADC ve doğrulama sınırı

Oluşturucu `PlayPublisherOAuth` nesnesini tembel olarak bağlar. Gerçek
kimlik bilgileri ilk yetkili sağlayıcı isteğinde ADC üzerinden yüklenir;
tam servis hesabı kimliği ve `androidpublisher` kapsamı kontrol edilir.
`ORBA_PLAY_OAUTH_ENABLED=NO` sonradan uygulanırsa önbellekteki belirteç de
kullanılmaz. Play Console yetkileri ve gerçek Google bağlantısı çalışma
zamanı yapılandırmasının başarılı olmasından ayrıca doğrulanmalıdır.

Yerel testler sentetik public key ve sahte OAuth fabrikaları kullanır;
ADC, ödeme veya canlı Google aboneliği doğrulaması yapmaz:

```sh
python -m pip install -r server/requirements.txt -r server/requirements-postgres.txt
python -m unittest -v server.tests.test_play_runtime
```

PostgreSQL bağımlılığı yalnız en az bir Play bileşeni açıkken yüklenir.
Kapalı yapılandırmada çekirdek sunucu bu bağımlılık olmadan da kurulabilir.

## Başlatma ve salt okunur hazırlık denetimi

`python -m server.gateway` yapılandırma oluşturucuyu HTTP dinleyicisinden ve
uygulama veritabanını açmadan önce çağırır. Eksik kısmi etkinleştirmede süreç
hata koduyla çıkar; bayrakları sessizce yok sayıp etkin görünmez.
Docker imajı PostgreSQL bağımlılığını içerir ve UID 10001 ile çalışır.

```sh
# Varsayılan: ağ/ADC/veritabanı çağrısı yok. Kapalı durum exit 2 verir.
python -m server.play_preflight
# Yalnız açıkça seçilen gerçek kontroller; hiçbir tablo kurulmaz.
python -m server.play_preflight --check-database
python -m server.play_preflight --check-oauth
# Özel 0600/0400 dosya: token argümana veya çıktıya yazılmaz.
python -m server.play_preflight --check-google --purchase-token-file /private/play-token --product PRODUCT_ID
```

Google smoke yalnız salt okunur GET yapar; ACK, sahip bağlama, snapshot veya
ödeme işlemi yapmaz. OAuth başarısı Play Console yetkisi kanıtı değildir.
`ok` yalnız istenen denetimlerin sonucudur; `production_acceptance`,
`entitlement_granted` ve gerçek Pub/Sub OIDC kabulü ayrıca doğrulanır ve
araç bunları kendiliğinden onaylamaz.

Kurulum rolüyle şemayı açıkça `initialize_postgres_rtdn()` ile oluşturun.
Çalışma zamanı ayrı, superuser/createdb/createrole yetkisiz ve şemanın sahibi
olmayan bir rol kullanmalıdır. Şema için USAGE; owner tablosu ve snapshot
için SELECT/INSERT/UPDATE, audit için SELECT/INSERT gerekir. Owner satır
kilitleri UPDATE yetkisi gerektirir. Hazırlık aracı bu izinleri ve tabloların
kolon/anahtarlarını salt okunur transaction ile denetler; aşırı yetkili rolü
reddeder. Yönetici DSN'sini çalışma zamanı DSN'si olarak kullanmayın.

İmaj ve çalışma zamanı kontrolü:

```sh
docker build -f server/Dockerfile -t orba-runtime .
python scripts/test_orba_runtime_container.py --image orba-runtime
```

Kurumsal HTTPS proxy'si özel CA gerektirirse doğrulamayı kapatmak yerine
BuildKit `--secret id=pip_ca,src=/trusted/ca-bundle.pem` kullanın; CA yalnız
build adımına bağlanır. Test; salt okunur, root olmayan ve kaynak sınırları
olan yerel konteyneri başlatır; sağlık yanıtını, kapalı webhook'u, bağımlılıkları
ve eksik yapılandırmada güvenli durmayı doğrular. Google'a bağlanmaz.

## Kalan işletim sınırları

Google transport çağrılarında tek istek için en fazla 8 saniye timeout vardır;
bu toplam OAuth retry süresi taahhüdü değildir. Webhook'un eşzamanlı işleme
kapasitesi 4'tür; dolu durumda 503 döner ve Pub/Sub yeniden teslim edebilir.
TLS, yavaş istemci ve istek hızı sınırları güvenilir ters proxy'de kurulmalıdır.

Mevcut owner/device kimliği tek sahibin çift P-256 protokolüdür. Nonce deposu
yerel özel SQLite dosyasıdır; ayrı nonce dosyalarıyla birden fazla owner
gateway replikası çalıştırmayın. Çok gateway için ortak replay deposu veya
açık bir tek-instance dağıtım sınırı gerekir. RTDN/billing kayıtlarının
PostgreSQL'de paylaşılması bu kimlik altyapısını kendiliğinden değiştirmez.

Gerçek ADC/Play Console uygulama ve ürün yetkisi, Google imzalı Pub/Sub
teslimi, lisans-test satın alması, gerçek cihaz ve owner-controlled release
imzası bu yerel/CI kontrollerinden ayrı kabul maddeleridir. Kaynakta olmayan
V41 testleri veya OMEGA'nın özgün 100 maddesi tamamlanmış sayılmaz.
