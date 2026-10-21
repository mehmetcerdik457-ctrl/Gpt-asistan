# KRAL / CİHAT — GitHub görev köprüsü (danışma modu)

## Sınır ve kaynak

Bu köprü mevcut `server.gateway.OpenAIProvider` katmanını yeniden kullanır. `Gpt-asistan` kodu ile CİHAT AI 3.2.1 APKM'nin özel model ağırlıklarının veya sunucularının aynı olduğu **kanıtlanmamıştır**. Bu işlem model çıkarma değildir.

ChatGPT'nin bağlı GitHub uygulaması ile aynı depoda bir **issue** oluşturulabilir. `cihat-task` etiketini yalnız depo sahibi kendi açtığı ve hassas bilgi içermeyen bir issue'ya eklerse, bu dal `main` içine ayrı onayla alındıktan ve sunucu tarafı sağlayıcı kurulumu yapıldıktan sonra GitHub Actions yalnızca **danışma yanıtı** üretir. Yanıt issue yorumuna gelir; buradaki ChatGPT yanıtı daha sonra okuyabilir. GitHub Actions sürekli çalışan sunucu değildir.

**Köprü komut çalıştırmaz, GitHub kodunu değiştirmez, APK kurmaz, telefona dokunmaz ve diğer depolara erişmez.** GitHub issue yazar kontrolü, OMEGA'nın telefon + Owner P-256 kimlik doğrulaması yerine geçmez. Gerçek görev yürütmesi için ayrı imzalı Owner onayı, izole çalışma, yetki listesi, test ve PR gerekir.

## Etkinleşme

1. Önce kaynak dalının testlerini CI'da doğrula. `main`e izinsiz birleştirme yapma.
2. İş sahibinin onayıyla workflow'un **varsayılan dalda** bulunması gerekir. Aksi hâlde `issues` olayı workflow'u tetiklemez.
3. Repo Actions Secrets içine `KRAL_OPENAI_API_KEY`, repo Actions Variables içine `KRAL_ALLOWED_MODELS` (gerçek erişilebilir modellerden en fazla dört tane) kaydedilir. Gizli anahtarları issue, yorum, PR veya APK içine yazma. Bunlar henüz kurulmuş kabul edilmez.
4. `cihat-task` GitHub etiketi oluşturulup depo sahibinin **kendisi** tarafından açılmış kamuya açık paylaşılabilir bir issue'ya uygulanır. Etiket tek başına yüksek yetki sağlamaz.
5. Gerçek çalışma kabulü: workflow run URL + canlı provider yanıtı + issue yorum ID. Bunlar olmadan canlı model yanıtı başarılı sayılmaz.

## Olumsuz testler

- Yanlış depo, yabancı issue yazarı, farklı etiket, kapalı issue, PR ve aşırı uzun istek reddedilir.
- Model veya API anahtarı eksikse görev tamamlandı iddiası üretilmez.
- Tekrar etiketlemede önceki marker kontrol edilerek aynı yanıtın iki kez gönderilmesi önlenir (100 yorum olursa fail-closed).
- Varsayılan dalda etkinleşene kadar otomatik issue tetikleyicisi çalışıyor iddia edilemez.
- Bu aşama herhangi bir kod değişikliği, telefon eylemi veya OMEGA `main` birleşimini kabul etmez.

## İki gerçek GitHub görev türü (güvenli başlangıç)

- **`[KRAL-CHECK] Kaynak testlerini doğrula`** başlıklı ve depo sahibi tarafından açılmış GitHub Issue: GitHub Actions, yalnız sabit `python -m unittest discover -s server/tests -v` komutunu çalıştırır; PASS değilse yorum yazmaz. PASS olduğunda test sayısını, gerçek workflow koşumunu ve commit SHA'yı issue yorumuna yazar. **Bu yol model anahtarı gerektirmez.** CİHAT'ın canlı cevap verdiğini iddia etmez.
- **`cihat-task` etiketi** yalnız depo sahibinin açtığı Issue'ya eklendiğinde: aynı sabit testlerden sonra mevcut `server.gateway.OpenAIProvider` ile *danışma yanıtı* oluşturmayı dener. Gerçek `KRAL_OPENAI_API_KEY` ve erişilebilir `KRAL_ALLOWED_MODELS` olmadan model yanıtı vermez. Bu mevcut CİHAT APK'nın özgün backend'i olarak sunulamaz.

İki tür de **yalnız workflow varsayılan dalda olduğunda** Issue olaylarıyla otomatik tetiklenir. Bu PR taslak ve birleştirilmemiş durumdayken açık Issue #40'a otomatik cevap geleceğini iddia etmiyoruz. Güvenli GitHub Issue yazarlığı, gerçek Owner + telefon P-256 cihaz yetkisinin yerine geçmez.

İyileştirmeler: GitHub HTTP yönlendirmeleri engellenir (yetki bilgisini başka hosta gönderme yok); sabit yorum yolu/metodu korunur; başka kullanıcıların sahte marker yorumları tamamlandı sayılmaz; test sonucu logdan okunur ve ham log Issue içine kopyalanmaz.
