# KRAL + CİHAT: Türkçe sesli taslak entegrasyonu

Kaynak: `integration/cihat-github-task-bridge-20261021` @ `7b06d7f2ccfdf44654470ee632132c5b995ac949`.
Bu çalışma ayrı bir entegrasyon dalında önceki PR #42 sesli taslak kodunu yeniden kullanır.

- Uygulama yalnız kilit açıldıktan sonra **Sesle yaz** düğmesini gösterir.
- Düğme önce mikrofon/konuşma hizmetiyle ilgili veri işleme uyarısı gösterir.
- Açık onay üzerine Android `RecognizerIntent` çağrılır. Sistemde konuşma tanıma uygulaması yoksa işlem reddedilir.
- Tanınan sonuç önce cihaz kilidi yeniden doğrulanarak mevcut taslağa eklenir.
- **Otomatik model isteği, CİHAT mesajı, sohbet kaydı veya hafıza aktarımı yapılmaz.**
- Şifreli yerel hafıza, CİHAT kimlik denetimi ve mevcut Owner/Gateway sözleşmesi değiştirilmez.

`SpeechDraftTest`: boş dönüş, Türkçe boşluklar, birleştirme, çoklu hipotez ve uzunluk sınırı.
`OwnerLockTest`: kilit ekranında sesli yaz düğmesi görünmez.

CI başarısı Android'de sistem konuşma tanıma servisinin gerçek telefon üzerinde çalıştığını doğrulamaz.
