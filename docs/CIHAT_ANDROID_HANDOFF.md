# KRAL → Mevcut CİHAT Android uygulaması: kullanıcı kontrollü açılış

**Kaynak:** Drive'daki `CİHAT_AI_BOT__SOURCE_OF_TRUTH__READ_ONLY` envanterinin `20_MACHINE_READABLE_INVENTORY.json` içinde CİHAT AI 3.2.1 paketinin `com.codespaceapps.aichat`, MainActivity'nin `exported=true` ve `android.intent.action.MAIN` / `android.intent.category.LAUNCHER` tanımı doğrulanmıştır. Manifestte standart `android.intent.action.SEND` desteği bulunmadığı için **otomatik mesaj gönderme veya özel deep-link iddiası yapılmıyor**. Bunlar statik APK manifest bulgularıdır, gerçek telefon testi değildir.

Mevcut `MainActivity.kt` içine **"CİHAT AI'ı aç (mevcut uygulama)"** tuşu eklendi. Telefonun cihaz kilidiyle açılmış KRAL oturumunda, paket görünürlüğü sorgulanır; kurulu/başlatılabilir değilse eylem durdurulur. Kuruluysa kullanıcı onay penceresinde "Yalnız aç", "Vazgeç" veya yalnız boş olmayan en fazla 2000 karakterlik **o an yazılmış taslak** için "Metni kopyala ve aç" seçeneklerini görür.

Android panosu gizli paylaşım kanalı değildir: metin başka uygulamalarda görülebilir. Bu nedenle yalnız açık onayla kopyalanır; API anahtarı, kişisel hafıza, sohbet geçmişi veya eski bot veri tabanları otomatik aktarılmaz. Android 13+ üzerinde pano öğesine hassas içerik etiketi eklenir. KRAL'dan çıkıldığında normal Android `onStop` cihaz kilidi politikası korunur.

Bu **uçtan uca CİHAT mesajı otomasyonu değildir**: CİHAT açıldıktan sonra kullanıcı metni kendisi yapıştırır ve gönderir. Eski bot veya APK değiştirilmez. `CihatHandoffTest.kt` taslak girdisi politikasını kontrol eder; emülatör/gerçek telefon testi ve kullanıcının CİHAT uygulaması kurulu olması gereklidir.

## Manuel CİHAT → KRAL dönüşü (yeni uygulama kodu)

CİHAT içinde kullanıcı bir yanıtı **kendisi kopyalar**, KRAL'a geri döner, cihaz kilidini açar ve **“CİHAT yanıtını panodan al (önizleme)”** seçeneğini tıklar. KRAL yalnız `text/plain` tek öğeli panoyu, en fazla 2000 karakterle ve kontrol karakterlerini reddederek önizler. **Taslağa aktar** onayı verilirse metin yalnızca yazı alanına alınır: **otomatik gönderim yok, hafıza/sohbet kaydı yok**. Var olan taslağın üzerine yazılacağı bildirilir. Kilit açılmadan bu kontrol görünmez.

**Gerçek sınır:** Android panosundaki metnin CİHAT kaynaklı olduğu doğrulanamaz. Bu kullanıcı kontrollü geçiştir; özgün CİHAT API'sine bağlandığı, arka planda sohbeti okuyabildiği veya fiziksel telefonda çalıştığı anlamına gelmez. Eski APK değiştirilmez. JVM ve emülatör negatif-kilit testleri eklenmiştir; gerçek cihaz testi ayrıca gereklidir.
