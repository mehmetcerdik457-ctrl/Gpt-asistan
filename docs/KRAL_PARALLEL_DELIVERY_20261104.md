# KRAL Genesis paralel teslim — 4 Kasım 2026

Bu çalışma mevcut `mehmetcerdik457-ctrl/Gpt-asistan` uygulamasını sürdürür.
Başlangıç commit'i `f2fd46a3c6edfae4f37d2e78669418f00cb33d41`;
entegrasyon dalı `kral-genesis-parallel-20261104`.
Kullanıcının bu oturumdaki açık talebi, doğrulanmış değişikliklerin `main`
dalına alınmasını ve GitHub Actions üzerinden APK teslimini yetkilendirir.
Eski günlüklerdeki ayrı merge izni sınırı bu çalışma için güncellenmiştir.

## Eş zamanlı iş dağılımı

Oturum kapasitesi bir koordinatör ve altı alt ajandır. Android arayüzü ve
taslak/ses; OTP/SMTP; release imzası; kabul testleri; CI/CD; bağımsız teslim
denetimi ayrı alanlarda eş zamanlı yürütülür. 12 fiziksel ajan, 50 çalışan
veya 8 alarm çalıştırıldığı iddia edilmez. Uygulamanın 12 uzman profili ve
50 mantıksal görev yuvası, bu kodlama oturumunun ajan kapasitesi değildir.

## Teslim ve doğrulama kuralları

- Her APK'nın kaynak commit'i, SHA-256 değeri, paket/sürümü, sertifikası ve
  test özetleri aynı Actions çalışmasında kaydedilir.
- Sahip anahtarı yalnız güvenilen bağlamda kullanılır; genel sertifika pini
  doğrulanmadan release imzası başarılı sayılmaz. Eksik anahtar başka bir
  üretim kimliği oluşturularak tamamlanmaz.
- Debug adayı ile sahip imzalı release ayrı adlarla ve doğru durumla sunulur.
- T01–T26 başlıkları test adımlarının yerine geçirilmez. Ayrıntılı durum
  [kabul raporunda](KRAL_PARALLEL_ACCEPTANCE_20261104.md) bulunur.
- SMTP kodu testlerde yerel taklitlerle doğrulanır. Gerçek sunucu/SMTP
  yapılandırması bulunmadan canlı e-posta teslimi iddia edilmez.
- Fiziksel telefonda yükseltme, gerçek biyometri, mikrofon/hoparlör ve canlı
  model erişimi emülatör sonucuyla doğrulanmış sayılmaz.

## Çalıştırma

```sh
python -m pip install -r server/requirements.txt
python -m unittest discover -s server/tests -v
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest :app:assembleRelease :app:bundleRelease --no-daemon --stacktrace
```

Sonuç ve indirme bağlantıları, exact kaynak commit'inin başarılı Actions
çalışması ve GitHub Release kayıtlarından okunmalıdır; önceki commit'in
test sonuçları yeni commit'e aitmiş gibi kullanılamaz.
