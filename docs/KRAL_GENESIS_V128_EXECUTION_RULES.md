# KRAL GENESIS 3.0 — V128 Çalışma ve İcra Kuralları

> Durum: uygulayıcı ajanlar ve geliştiriciler için **çalışma talimatı**. Bu dosyanın varlığı herhangi bir ajanı, CI işçisini veya arka plan sürecini kendiliğinden başlatmaz.

## Tek kaynak ve hedef
- Tek ana şartname: `KRAL_GENESIS_3_0_TEK_NIHAI_YOL_HARITASI.pdf` veya aynı adlı `.md`; mevcut değilse kaynak eksikliğini açıkça bildir. Belgeyi okumadan 28 bölümün alt maddelerini tamamlanmış sayma.
- Kapsam: §0–§28, Faz 0–8, 13 aşamalı yetenek kazanımı, T01–T26 ve A/B/C nihai kabul.
- Nihai hedef: kullanıcı verilerini koruyan, sahibi tarafından kontrol edilen, gerçek cihazda doğrulanmış **tek KRAL Genesis Android APK**.
- Güncel dal/HEAD, PR, CI ve APK kimliği her çalışma başında yeniden doğrulanır; geçmiş raporlar tek başına canlı kanıt değildir.

## Çalışma döngüsü — rapor değil gerçek teslim
1. En son kaynak ve görev defterini oku; tamamlanmış ve engelli işleri ayır.
2. Bir sonraki en yüksek öncelikli, yetkili ve bağımsız işi seç.
3. Sorunu kod/test ile yeniden üret; küçük ve güvenli düzeltme uygula.
4. İlgili birim, entegrasyon, Android, güvenlik ve regresyon testlerini gerçekten çalıştır.
5. Sonuç başarılıysa ayrı geliştirme dalında commit ve PR oluştur; CI kanıtını kaydet. **main'e otomatik merge yapma.**
6. Test başarısızsa kök neden, log ve rollback yolunu kaydet; yanlış PASS üretme.
7. Görev ve bölüm durumunu güncelle, kullanıcıya somut kanıt bildir, sonra sıradaki bağımsız göreve geç. Her rutin adım için yeniden 'devam et' isteme.
8. Ortam/erişim yoksa tam uygulanabilir patch, test komutları ve tekil engel kaydı teslim et; erişim varmış gibi davranma.

## Zorunlu öncelik
- **P0:** 1.0.4/1.0.5/1.0.6 APK imzaları ve veri koruyan güncelleme; sahibi doğrulama ve yetkisiz komut reddi.
- **P1:** `MainActivity.kt` görev kimliği seçme/kopyalama ve ses tanıma sırasında Activity yeniden oluşturma kusurları; SQLCipher hafıza ve restore; gerçek backend/model çağrısı.
- **P2:** OMEGA sözleşmeleri, offline/online, ajan görev yürütücüsü ve ses regresyonları.
- Eski APK'yı kaldırma veya veriyi silme; önce güvenilir yedek/geri yükleme ve imza uyumunu doğrula.
- `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`, `ANDROID_STORE_PASSWORD` değerlerini hiçbir rapora, PR'a, sohbete veya kaynak koda yazma. `BLOCKED_OWNER_SECRETS_MISSING` gerçek owner-signed teslim değildir.

## Gerçeklik ve güvenlik
- `.agent.md` = rol tanımı, **canlı ajan değil**. Dalın varlığı = entegre çalışan özellik değil. CI worker = model değil.
- Model önerir; güvenlik çekirdeği yetkilendirir; yürütücü uygular; bağımsız denetçi doğrular.
- Least privilege, varsayılan read-only/dry-run, fail-closed, audit trail, idempotency ve rollback uygula.
- Üretim dağıtımı, `main` merge, secret/OAuth değişikliği, kalıcı hesap izni, veri silme ve diğer kritik dış eylemler için açık sahip onayı al.
- Gerçek telefon, canlı model, imza, Drive teslimi veya güvenlik testi yapılmadıysa **NOT_TESTED/BLOCKED** olarak yaz; tamamlandı deme.

## Durum defteri
Her bölüm/alt madde için `NOT_STARTED | IN_PROGRESS | CODE_COMPLETE | TESTING | VERIFIED | BLOCKED | FAILED | ACCEPTED` kullan.
Kanıt alanları: şartname maddesi, dosya/satır, commit SHA, PR URL, CI run URL, test komutu/sonucu, APK SHA-256, cihaz/imza doğrulaması, engel ve sonraki görev.
T01–T26 ayrı `PASS | FAIL | BLOCKED | NOT_TESTED` matrisiyle tutulur. Sadece bütün zorunlu alt koşullar geçince `ACCEPTED` yazılır.
İlerleme yüzdesi, aktif uzman ve model sayıları uydurulmaz.

## Her turda zorunlu çıktı
```text
KRAL V128 — GERÇEK İLERLEME
ŞU ANDAKİ BÖLÜM: §X / görev
BU TUR GERÇEKTEN YAPILAN: [kod/test/patch]
TAMAMLANAN: [kanıtlı maddeler]
KANIT: [commit, PR, CI, dosya, test sonucu]
KALAN: [açık maddeler]
ENGELLER: [kesin neden, gerekiyorsa tek yetki]
T01–T26: [PASS / FAIL / BLOCKED / NOT_TESTED sayıları]
SONRAKİ İŞLEM: [uygulanabilir kesin görev]
```
Bir bölüm kabul edildiğinde: **“BÖLÜM X TAMAMLANDI VE KANITLANDI. ŞİMDİ BÖLÜM Y ÜZERİNDEYİM.”**
Engelliyse: **“BÖLÜM X ENGELLİ: ... BAĞIMSIZ BÖLÜM Y İLE DEVAM EDİYORUM.”**

## Nihai durdurma koşulu
T01–T26 PASS, tüm zorunlu şartname maddeleri ACCEPTED, gerçek cihaz testi, güvenli güncelleme, canlı model/araç kabulü, imzalı APK ve tekrar indirilen teslim hash doğrulaması tamamlanmadan **%100 veya FULL_ACCEPTANCE=YES** ilan etme.
