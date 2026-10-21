# KRAL/CİHAT — 1.0.3 denemesini önceki 1.0.4 verilerini silmeden kurma

## Sorunun gerçek kanıtı

- Önceki GitHub PR #39 derlemesi (`9425a9d7`): Android debug paketi `com.example.gptasistan.genesis`, sürüm kodu **4**, sertifika SHA-256 `c71f983fefc3856b26a3b8ee3036b7c06cc3fdaefd08297071cfa2d6959b722a`; [CI ve APK metaverisi](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/39673780555).
- Google Drive `GENESIS_MEHMET_MASTER_2026-10-20/TESLIM` içindeki 1.0.4 kayıtları: `com.example.gptasistan.genesis`, sürüm kodu **5**; `apk-signature.txt` sertifika SHA-256 `122074f2a4dbd5ec3244fb1817829788d4f067ee681bc1e012adf3ebcef5ba42`. Bunlar *Drive kayıtlarından* okundu; oradaki 1.0.4 APK gerçek cihazda denenmedi.
- **Aynı paket + farklı imza** = güvenli Android üstüne yükleme değil. Sadece sürüm numarası artırmak çözüm olmaz. Mevcut 1.0.4'ü kaldırarak geçiş yapmak kullanıcı verisini silebilir. Orijinal CİHAT 3.2.1 başka pakettir: `com.codespaceapps.aichat`.

## Aynı mevcut Android projesinde yaptığımız güvenli ayrıştırma

PR #39'un bu deneme dalında Gradle `debug.applicationIdSuffix` artık `.genesis.cihatpreview` değerini kullanır. Yeni debug paket:

```
com.example.gptasistan.genesis.cihatpreview
```

Yeni APK launcher etiketi `KRAL CİHAT Önizleme`; sürüm adı `1.0.3-genesis-cihat-preview`. Böylece Android bunu daha önceki `com.example.gptasistan.genesis` uygulamasının güncellemesi saymaz ve **ayrı uygulama alanı / ayrı özel SQLite** oluşturur. Önceki hafıza kendiliğinden kopyalanmaz, silinmez. Bu, nihai birleştirme sürümü değil, kontrollü yan yana entegrasyon denemesidir.

GitHub Android workflow'u `scripts/android_artifact.py --expected-package com.example.gptasistan.genesis.cihatpreview` ile paket kimliğini **APK'nin gerçek manifestinden** kontrol eder. Farklı paket bulunursa artefakt üretimi fail-closed olur. Emülatör smoke testi aynı uygulama kimliğiyle yükleme/açılış ve Owner kilidi kontrolünü yapar. `server/tests/test_android_preview_identity.py` eski/yanlış paket adlarının reddini sınar.

## Kabul koşulları

1. GitHub aynı HEAD için Python CI + Android build/lint/JVM + emülatör joblarını başarıyla bitirmeli.
2. Üretilen **yeni** APK'nin `apk-metadata.json` içindeki `package` değeri `com.example.gptasistan.genesis.cihatpreview` olmalı; gerçek SHA-256 ve sertifika kaydedilmeli.
3. Eski 1.0.4 ve CİHAT 3.2.1 telefon üzerinde *korunmalı*. Kullanıcıdan hiçbir eski uygulamayı kaldırması veya veri temizlemesi istenmemeli.
4. Gerçek telefonda CİHAT kurulu açılış ve manuel yanıt dönüşü, kullanıcının yetkili onayıyla ayrıca sınanmalı. Owner kilidi ve gizli hafıza aktarımları onaylanmadan otomatik eylem açılmaz.
5. Model API'si ve gerçek telefon kabulü olmadan `LIVE_MODEL_ACCEPTED` / `PHYSICAL_DEVICE_ACCEPTED` **false** kalmalı.

Bu kararla mevcut Android kaynakları yeniden yazılmadı; yalnız güvenli debug sürüm kimliği ve teslim testleri düzeltildi. Nihai tek ürün göçü, imza zinciri ve kişisel verilerin izinli aktarımı ayrıca tasarlanmalıdır.
