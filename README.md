KRAL Genesis 3.0, mevcut Android uygulaması ve ona eşlik eden Python sahip
geçidi üzerinden geliştirilir. Android uygulaması şifreli yerel geçmiş,
taslak/ses girişi, cihaz kilidi ve imzalı uzman görev istemcisini içerir.

- [Derleme ve APK teslimi](docs/KRAL_PARALLEL_DELIVERY_20261104.md)
- [T01–T26 kabul kanıtı](docs/KRAL_PARALLEL_ACCEPTANCE_20261104.md)
- [E-posta OTP ve sunucu yapılandırması](docs/KRAL_EMAIL_OTP.md)
- [Önceki çalışma kayıtları](KRAL_MASTER_PROGRESS.md)

Android için JDK 17 ve SDK 36 kullanılır. GitHub Actions JVM testlerini,
Lint denetimini ve API 30/36 emülatör testlerini çalıştırır. Python testleri:

```sh
python -m pip install -r server/requirements.txt
python -m unittest discover -s server/tests -v
```

İmzalama veya SMTP sırrı kaynak koduna ve APK'ya konulmaz. Debug adayının
telefon üzerindeki mevcut kurulumla yükseltme uyumluluğu ayrıca doğrulanmalıdır;
imza uyuşmazlığını gidermek için uygulama verisini silmeyin.
