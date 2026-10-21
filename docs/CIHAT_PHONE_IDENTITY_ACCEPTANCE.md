# CİHAT 3.2.1 — gerçek telefon kimlik kontrolü ve kabul engeli

**Kaynak:** Kullanıcının Google Drive `CİHAT_AI_BOT__SOURCE_OF_TRUTH__READ_ONLY/19_FINAL_VERIFICATION_REPORT.md` ve `CIHAT_AI_STATIC_FORENSIC_REPORT (1).md` statik inceleme kayıtları: `com.codespaceapps.aichat`, `versionCode=893`, `versionName=3.2.1`, imza sertifika SHA-256 `7b4a4b483ad4fdfa7bcab3c4ba9fd5a0461cab208fc7120a4d8d2f4901b3a097`. Bu kayıtlar **bir referanstır, güncel telefonda aynı uygulamanın kurulu olduğunun kanıtı değildir.**

## Bu dalda gerçek uygulama değişikliği

`CihatIdentity.kt`, Android PackageManager üzerinden kurulu CİHAT'ın **tam paketini, sürüm kodunu, mevcut APK sertifikasını ve başlatılabilirliğini** kontrol eder. Bilinmeyen sürüm, eski rapordakinden farklı imza, birden fazla imza, eksik paket veya açılamayan giriş etkinliği durumunda fail-closed sonuç döner. Android API 26–27 ve 28+ imza API'ları kapsanır.

KRAL'da cihaz kilidi açılmışken **“CİHAT kurulumunu doğrula (salt okunur)”** ekranı kurulu paket ve imza durumunu gösterir; özel sohbet okumaz, ağa bağlanmaz, dosya aktarmayı veya kaldırmayı denemez. Var olan **“CİHAT AI'ı aç”** düğmesi sadece `VERIFIED_321` sonucunda (ve kullanıcının açık onayından sonra) çalışır. Bu, sahte paket/yanlış sürüm ile karışmayı engeller.

## Kabul adımları

1. Yeni **`com.example.gptasistan.genesis.cihatpreview`** debug adayı, eski KRAL ve CİHAT APK'larına dokunmadan **ayrı kurulum** olarak açılmalı.
2. Kullanıcı cihaz kilidini açıp **“CİHAT kurulumunu doğrula (salt okunur)”** düğmesine dokunmalı; bu düğme **gerçek telefondaki** sürüm ve sertifikayı gösterir. `VERIFIED_321` olmadan CİHAT'a handoff yapılamaz.
3. Kullanıcı açık onayla KRAL'dan CİHAT'ı açıp, kendi test sorusunu CİHAT'ta yapıştırıp gönderebilir; CİHAT yanıtını kendi seçerek kopyalayıp KRAL'a dönerek onaylı önizlemeyle taslağa aktarabilir.
4. Yukarıdaki işlemler gerçekte yapılıp kanıtlanmadıkça **PHYSICAL_CIHAT_HANDOFF=NOT_TESTED** kalır. CİHAT yanıtı otomatik alınmaz; clipboard kökeni doğrulanamaz.
5. Telefonda başka sürüm varsa sakın kaldırma veya veri silme. Bu kod yalnız eldeki 3.2.1 (893) için sabit referansı kabul eder; yeni sürüm için ayrı kaynak/imza denetimi gerekir.

**Sınırlama:** Uygulama paketi ve imza eşleştirmesi gerçek **Owner kimlik doğrulaması** veya CİHAT'ın özel backend/model servisinde API kullanım yetkisi değildir. Ağ, model, otomasyon ve üretim kabulü bu aşamada kapalı kalır. Testler gerçek telefonun yerine geçmez.
