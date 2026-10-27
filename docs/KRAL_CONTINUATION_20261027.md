# KRAL adayının paket ve yetkilendirme doğrulaması

Bu devam çalışması `integration/kral-asistan-20261020` dalının
`548749d5d7684d183ce9551803fabda6e4e26172` commit'ini temel alır. Daha eski
raporlardaki kaynak ve APK'lar güncel dalın test sonucu sayılmaz.

## Paket ve imza sınırı

Debug ve release varyantlarının uygulama kimliği
`com.example.gptasistan.genesis` olarak sabittir. Namespace değişmez.
Bu kimlik, orijinal `com.example.gptasistan` uygulamasından ve tarihsel
`com.example.gptasistan.candidate` adayından ayrıdır. Eski uygulamanın
verileri otomatik taşınmaz. Aynı `.genesis` kimliğine sahip kurulu başka
bir aday varsa güncelleme uyumluluğu ayrıca imza ve sürümle doğrulanmalıdır.

Teslim betiği beklenmeyen paket kimliğini reddeder. Release olarak
doğrulamada debug APK kabul edilmez ve beklenen imza sertifikasının tam
SHA-256 değeri gerekir. APK dosyasının SHA-256 değeri ile imza
sertifikasının SHA-256 değeri farklı alanlarda tutulur.

Yeni yayın anahtarı üretilmedi. Mevcut CI debug APK üretir; bu APK kalıcı
release anahtarıyla imzalı yayın sürümü olarak sunulamaz. İmza anahtarı,
parola dosyası ve PKCS#12 dosyaları kaynak arşivine eklenmez.

## Doğrulama

```sh
python -m pip install -r server/requirements.txt
python -m unittest discover -s scripts/tests -v
python -m unittest discover -s server/tests -v
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleRelease --no-daemon
```

Python artifact testleri sentetik APK/araç çıktıları kullanır; gerçek
APK'nın imza doğrulaması CI'de Android `apksigner` ile ayrıca yapılır.
Sunucu testleri yerel HTTP sunucusu ve gerçek P-256 imzaları kullanır;
model sağlayıcısı sentetiktir. Bu testler canlı model çağrısı değildir.
Yetkisiz sohbet geçmişi/bellek erişimi ile yinelenen yetki ve gövde
uzunluğu başlıkları HTTP sınırında reddedilmelidir.

Android CI, kaynak commit'ini, APK hash'ini ve imzayı kaydeder. Emülatör
işi aynı APK'yı hash kontrolünden geçirerek kurar ve sahip kilit ekranını
denetler. Bu kapsam fiziksel telefon, biyometri, gerçek ses çıktısı veya
canlı model kabulü değildir.

CI ayrıca imzasız release varyantını derleyip gerçek manifestten aday
paket kimliğini ve debug kapalı durumunu kontrol eder. Yalnız kontrol
sonucu kanıt paketine girer; imzasız release APK teslim edilmez.

## Canlı test için gereken gerçek girdiler

- Yetkili HTTPS Owner Gateway adresi ve çalışan sunucu.
- Android'den dışa aktarılan açık anahtar kaydının, gerçek sahip
  doğrulamasından sonra sunucuda kaydedilmesi.
- Sağlayıcı anahtarının sunucunun gizli değer yönetimine eklenmesi ve
  izinli model listesi. Anahtar sohbete, APK'ya veya depoya konmaz.
- Fiziksel cihaz erişimi ve ayrıca belirlenmiş model kullanım bütçesi.

Bu girdiler olmadan canlı sağlayıcı, fiziksel cihaz ve üretime dağıtım
sonuçları `NOT_EXECUTED` olarak kalır. Başarılı `/api/health` sonucu
sahip doğrulaması veya gerçek model erişimi kanıtı değildir.
