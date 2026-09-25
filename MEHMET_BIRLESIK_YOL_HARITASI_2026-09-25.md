# MEHMET AI — Birleşik hedef, APK karşılaştırması ve uygulanabilir yol haritası
Tarih: 25 Eylül 2026 — Europe/Istanbul
Proje sahibi: Mehmet Cerdik
Belge türü: Kanıta dayalı durum tespiti + önerilen uygulama ve kabul sözleşmesi.
Bu belge yazılımın tamamlandığı veya production OWNER yetkisi atandığı anlamına gelmez.

## 1. Bittiğinde Mehmet'in elinde ne olacak?
Hedef: Mehmet'in tercih ettiği mevcut uygulamayı kullanırken kendisini tanıyan, izin verdiği bilgileri kalıcı saklayan ve sonraki konuşmalarda doğru kullanan, mevcut ve yetkili modeller arasında görevine uygun seçim yapan, bağlı araçlarla iş yapan, sonucu doğrulayan, hataları kaydederek sonraki denemelerde kullanan kişisel AI sistemi.

Aynı public uygulama ana kullanım yüzeyi olarak korunur. Bunun için o uygulamanın mevcut entegrasyon/hesap yetkilendirme desteği veya yetkili ürün geliştiricisinin resmî sürüm değişikliği gerekir. APK'yı patch etmek veya ayrı Companion'ı “aynı public ürün” diye sunmak çözüm sayılmaz.

Bütün model ağırlıklarına sahip olma, sağlayıcı sınırlarını kaldırma, sınırsız ücretsiz kullanım veya kusursuz hafıza vaat edilmez. OWNER rolü erişim yönetir; zeka, hafıza ve araç yürütmesi ayrı çalışan bileşenlerdir. Yeni bir temel model eğitmek gerekmiyor.

## 2. Kanıt dili ve araştırma sınırı
- VERIFIED_THIS_RUN: Bu tur API cevabı, kaynak kod veya dosya baytları üzerinden doğrudan doğrulandı.
- OBSERVED_RECORD: Güncel kayıt okundu; kaydın anlattığı olayın ham çalışma kanıtı bu tur yeniden yürütülmedi.
- INFERRED: Açıkça belirtilen teknik çıkarım.
- UNKNOWN: Kanıt yetersiz. YOK anlamına gelmez.
- PROPOSED: Bu raporun önerdiği iş veya kabul ölçütü; yapılmış iş değildir.

Kapsam: GitHub depo/PR/CI/artifact metadata; belirli Java/manifest/build dosyaları; mevcut Drive durum ve sahiplik denetimi; Library'deki public APKM ve düzeltilmiş Owner APK; resmî Android/Firebase belgeleri ve iki birincil araştırma kaynağı.

Bu tur telefona bağlanılmadı, uygulama kurulmadı, public backend üzerinde sorgu/rol atama denenmedi, mevcut anahtarlar çıkarılmadı/kullanılmadı. Kriptografik APK imza doğrulama aracı çalıştırılmadı: sertifika parmak izi okundu, ZIP CRC ve dosya hashleri hesaplandı. Dolayısıyla yeni bir imza-PASS iddiası yok.

## 3. Sahiplikte kendi gözümle görülen ve açık kalan nokta
VERIFIED_THIS_RUN:
- GitHub deposu mehmetcerdik457-ctrl/Gpt-asistan, aynı GitHub hesabının deposu.
- Bağlı API cevabında admin/maintain/push/pull yetkileri true.
- main HEAD: 5062b22ccfc11bdd10302bed75e5902deeb4ea4c.
- PR #24 açık; HEAD f6cf3c087ebee514d54a9b55d1da58d39523c91f; ana dala birleşmemiş.
- Resmî Google Play sayfası com.codespaceapps.aichat için yayıncıyı Codespace Dijital olarak gösteriyor.

OBSERVED_RECORD:
- Bugünkü GUNCEL_DURUM kaydı, Mehmet'e ait farklı bir GCP projesinde yönetim/audit kanıtı bildiriyor.
- Aynı kayıtta public uygulamanın production projesi için hesap→IAM/OWNER bağı hâlâ NOT_PROVEN.
- Bugünkü CURRENT_STATE, Mehmet'in ayrı Railway backend'inde gerçek OpenAI çağrısı içeren başarılı dağıtım kaydı bildiriyor. Bu eski “API çağrısı henüz yok” durumundan ileridir; bu tur aynı çağrı tekrarlanmadı.
- Aynı kaydın en son bölümünde owner_auth_configured=false; backend'de model çalışması, son kullanıcı OWNER oturumunun tamamlandığı anlamına gelmez.

Hüküm: Mehmet'in kişisel AI geliştirmelerinin ve kendi deposunun varlığı kanıtlıdır. Bu kanıtın public uygulamanın production sunucusuyla yetki bağı aynı şey değildir. Yayıncının şirket adı, Mehmet'in şirketle ilişkisini tek başına doğrulamaz veya çürütmez. Bu ilişki UNKNOWN tutulur; “senin değildir” hükmü verilmez.

## 4. Güncel APK ve kaynak karşılaştırması
“En güncel” üç ayrı anlamda ele alındı: erişilen public binary, erişilen imzalı Owner binary, daha yeni kaynak geliştirmesi. Play sayfasında son güncelleme 15 Eylül 2026 görünüyor; bu sayfanın okunması 3.2.1'in tüm cihaz/bölgelerde en son dağıtılan sürüm olduğunu kanıtlamaz. Telefonda fiilen kurulu sürüm bu tur okunmadı.

| Özellik | Public Chatbot AI | Erişilen düzeltilmiş Owner | Daha yeni Owner geliştirmesi |
|---|---|---|---|
| Sürüm | 3.2.1 / 893 | 1.2.0 / 4 | Kaynakta 1.3.0 / 5 |
| Paket | com.codespaceapps.aichat | com.mehmetcerdik.ownerai | com.mehmetcerdik.ownerai |
| İncelenen şey | APKM içindeki 35 APK; base manifesti | İmzalı APK baytları ve manifest | PR #24 kaynak + CI/artifact metadata |
| INTERNET izni | Var | Yok | Manifestte var |
| Yeni OwnerBrainEngine/OwnerMemory sınıfları | Seçilmiş taramada eşleşme yok | Seçilmiş taramada eşleşme yok | Kaynakları mevcut ve okundu |
| Hafıza | Ürünün sunucu tarafı hafıza davranışı bu analizle bilinmiyor | Yeni PR24 hafıza modülü bu binary'de yok | SQLite kayıt var; modele hafıza bağlamı boş veriliyor |
| Model yolu | Ağ istemcisi/servis bileşenleri var; hesap yetkileri bilinmiyor | Doğrudan ağ üzerinden yeni beyin yolu yok | Yapılandırılabilir tek endpoint/model çağrısı |
| Telefon aracı | Bu incelemede genel telefon ajanı kanıtlanmadı | Ayrı Companion/Bridge hattı | Bridge üzerinden belirli araçlar ve sınırlı ajan döngüsü |
| Aynı public uygulamada OWNER | Kanıtlanmadı | Ayrı paket; bu hedefi kanıtlamaz | Ayrı paket; bu hedefi kanıtlamaz |
| Cihazda bütünleşik son ürün testi | Bu tur yapılmadı | Bu tur yapılmadı | Kanıtlanmadı |

Doğrudan hesaplanan kimlikler:
- Public APKM SHA-256: 7fee1649912638837e578658d49c5bf23007e04ac31829cb059032efb9f1f165
- Public base APK SHA-256: bbcf7838e942629ff4c7f6a25791d51ae76cad971f162d68d23e5f96bb600d65
- Public base: 77.308.245 bayt; minSdk 24; targetSdk 36; 8 DEX.
- Public APK v2 bloğundan okunan sertifika SHA-256: 7b4a4b483ad4fdfa7bcab3c4ba9fd5a0461cab208fc7120a4d8d2f4901b3a097
- Owner 1.2.0: 4.602.863 bayt; minSdk 24; targetSdk 35; 1 DEX.
- Owner APK SHA-256: be15d47df7573fe4da7500cbd31f5caf21df380f0084c623d6e7a4a5e15f84b7
- Owner APK v2 bloğundan okunan sertifika SHA-256: 279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448
- Owner DEX içinde beklenen c8b52661921f82d9e832a0dcf7eed514e970bf49 var; eski sentetik 464ce024b7678822e40eb48fea5b014d3dafb6a1 yok.
- İki incelenen APK'nın ZIP CRC kontrolü geçti.
- Önceki 55a179...5394 Owner hash'i güncel CURRENT_STATE içinde superseded olarak işaretli; son binary ile karıştırılmamalı.

PR24 doğrudan CI sonucu:
- İncelenen aynı HEAD için 8 run: 7 success, 1 failure.
- Phone Agent Emulator Validation run 36055244933: failure.
- Bu run'da unit test/build başarılı; “Execute phone-agent runtime in Android emulator” adımı başarısız; sonraki evidence verification skipped.
- Başarısızlığın kök nedeni bu raporda çözümlenmedi; uygulama hatası mı ortam hatası mı olduğu UNKNOWN.
- Build Stable Owner Companion run 36055249746: success.
- Artifact 10832491841: stable-owner-companion-unsigned-release; 3.699.139 bayt; arşiv digest 2ac02b9c3d78ba764a64932fe50dc7a43a13101642becd77ef1adcca31dcf4d3.
- Bu digest APK hash'i değildir. PR24 artifact baytları bu tur indirilmedi; imzalı 1.3.0 release doğrulanmadı.
- İncelenen Drive PR24 yedeği önceki 8e8bb4ea HEAD'ini taşıyor. O yedek güncel f6cf3c08 kanıtı diye kullanılamaz.

## 5. “Motor var; X8/anahtar verilince her şey olur” iddiası
X8'in tam teknik karşılığı mevcut ilgili kanıtlardan çözülemedi. SDK, API anahtarı, x86_64 veya bir uygulama ayarı olduğu varsayılmadı. İlgili ekran/metin gelirse ayrı bir kanıt satırıyla açıklığa kavuşturulacak; yol haritasının geri kalanı buna bağlı değil.

Public pakette Flutter/Dart native bileşenleri ve Firebase ile ilişkili izler var. Bütün 35 APK'nın seçilmiş marker taramasında ai-chat-codespace, is_premium, external_premium, experimentVariant metinleri bulundu. Bu metinlerin varlığı rol atama veya erişim izni değildir.

Base içinde OCR amaçlı TFLite dosyaları var. 35 APK'nın dosya adlarında .gguf/.safetensors/.onnx biçiminde genel model ağırlığı bulunmadı. Bu, gizli/özel formatlı veya sonradan indirilen modellerin yokluğunu ispatlamaz. libflutter.so arayüz/çalışma motorudur; kendi başına genel dil modelinin tüm zekâsını ve sunucu yetkilerini içerdiği söylenemez.

Firebase'in resmî belgesi, Firebase API anahtarının proje/uygulamayı tanımladığını ve tek başına backend kaynak erişimini vermediğini açıklar [R2]. App Check uygulama/cihaz doğruluğunu destekler; kullanıcı kimliği ve OWNER yetkisinin yerine geçmez [R3]. Remote Config, uygulamada uygulanmış davranışları ayarlayabilir; var olmayan yönetim ekranını veya hafıza sistemini yaratmaz. İstemciye dağıtılan Remote Config değerleri gizli yetki kasası sayılmaz [R4].

## 6. Kodda bulunan gerçek açıklar
1. OwnerBrainPolicy.providerMemoryContext() doğrudan “[]” döndürüyor. Gizli veriyi otomatik göndermeme amacı yerinde; ancak izinli, görevle ilgili hafızayı geri çağırma yolu yok. Kaydetme var, kişiselleştirilmiş hatırlama tamamlanmış değil.
2. OwnerMemory normal SQLiteOpenHelper ile metin saklıyor. İncelenen sınıfta uygulama düzeyinde şifreleme, silme/düzeltme arayüzü, kaynak/proje etiketi veya geri yükleme düzeni yok. Android'in cihaz şifrelemesi bu ayrı gereksinimleri kendiliğinden karşılamaz.
3. İncelenen OwnerBrainEngine tek yapılandırılmış endpoint/model çağırıyor. Çoklu sağlayıcı kapasite seçimi, maliyet limiti ve çalışan fallback router bu sınıfta yok.
4. Araç sonucu ok=true ve yeniden ekran okuma, hedefin gerçekten gerçekleştiğini tek başına kanıtlamıyor. Deterministik sonkoşul doğrulayıcısı gerekli.
5. allowTool içinde kelime eşleştirmesi kullanılıyor. Bu, işlem türü/hedefi/parametreleriyle bağlı yetkilendirme sözleşmesi değildir. Tasarımda bu katman güçlendirilmeli.
6. audit tablosunda detail_hash bulunuyor; satırları birbirine bağlayan ve silme/yeniden sıralamayı yakalayan bir audit zinciri bu sınıfta yok.
7. Modelden JSON parse edilemediğinde metin cevap olarak kabul edilebiliyor. “Model cevap verdi”, “geçerli araç planı üretildi” ve “görev başarıyla tamamlandı” ayrı sonuçlar olmalı.
8. Android beyni, ayrı çalışan backend ve public uygulama arasındaki üretim entegrasyonu hâlâ kanıtlanmış tek akış değil.

Bunlar kaynak incelemesi bulgularıdır; bu tur çalışan uygulamada güvenlik açığı üretimi veya istismar testi yapılmadı.

## 7. Tek birleşik uygulama sırası
Aşağıdaki kabul eşikleri bu proje için öneridir; tamamlanmış test sonucu değildir.

| Sıra | Yapılacak iş | Yeniden kullanılacak mevcut parça | Bitti sayılması için kanıt |
|---|---|---|---|
| 1 | Tek ürün/hesap/entegrasyon sözleşmesini sabitle | Public paket kimliği, mevcut depo ve sahiplik arşivi | Public ürün→yetkili yönetim yüzeyi→Mehmet hesap bağı; aynı uygulamanın desteklediği entegrasyon yolu |
| 2 | OWNER yetkisini gerçek hesap ve oturuma bağla | Varsa mevcut auth/rol altyapısı | Yetkili sunucu cevabı; normal test hesabının aynı işlemi reddedilmesi; oturum iptali |
| 3 | Mevcut modelleri çalışan ürün akışına bağla | Var olan backend/model çağrısı ve PR24 istemci kodu | Telefonun gerçek isteği→izinli model→gerçek cevap; sağlayıcı/süre/maliyet kaydı |
| 4 | Kalıcı hafızayı cevaba bağla | OwnerMemory ve mevcut arşiv | Kaydet→kapat→yeniden aç→ilgili bilgiyi getir→cevapta doğru kullan |
| 5 | Göreve göre model yönlendirmesini tamamla | Mevcut router çalışmaları | Gerçek erişilebilir modeller; kontrollü hata durumunda uygun fallback; limit aşımında durma |
| 6 | Araçları yetki ve sonkoşul doğrulamasıyla bağla | ToolBus/Bridge/bağlayıcılar | Okuma/yazma ayrımı; hedef/parametre kontrollü çağrı; bağımsız sonuç doğrulaması |
| 7 | Hata hafızası ve kurtarmayı ekle | Mevcut audit/recovery kayıtları | Hatanın sınıflandırılması; kör tekrarın engellenmesi; düzeltmenin sonraki görevde kullanılması |
| 8 | Aynı uygulama içindeki sahip yüzeyini tamamla | Mevcut ekran/entegrasyon varsa kullan | Mehmet hesabında açılır; normal kullanıcıda görünmez ve sunucuda da erişilemez |
| 9 | Gerçek telefon kabulü ve yedekten kurtarma | İmzalı sürüm hattı, verifier, Drive | Doğru paket/sürüm/hash ile cihaz testleri; geri yükleme; readback; rollback kaydı |

Sıra 1'in public ürüne özgü kısmı kapalıysa, kendi kaynaklarındaki hafıza/verify düzeltmeleri hazırlanabilir. Ancak bunlar SAME_PUBLIC_APP_OWNER_MODE tamamlandı diye raporlanmaz. Hedef sessizce ayrı uygulamaya çevrilmez. Kaynak değişikliği gerekiyorsa aynı resmî ürünün yetkili yayın süreci kullanılır; “binary hiç değişmesin ama olmayan ekran da eklensin” çelişkisi kabul edilmez.

## 8. Kalıcı beyin için uygulanabilir sözleşme
Her bilgi: id, proje, kaynak, oluşturma/güncelleme zamanı, geçerlilik dönemi, güven düzeyi, hassasiyet ve kullanıcı paylaşım tercihi taşır. Kitap/alinti, kullanıcı beyanı, araştırma sonucu ve model çıkarımı ayrı tutulur.

Akış: izinli kayıt → indeksleme → görevle ilgili erişim → izin/hassasiyet filtresi → modele gerekli minimum bağlam → kaynakla cevap. Eski ve yeni çelişirse sessizce birleştirilmez; düzeltme geçmişi tutulur. Bilinmeyende uydurma yapılmaz.

Varsayılan yaklaşım: mevcut yapı içinde metin/anahtar sözcük aramasıyla güvenilir geri çağırmayı tamamla; ancak ölçülen ihtiyaç varsa anlamsal arama ekle. Her görevde bütün arşivi sağlayıcıya gönderme. Özel hafızanın dış modele paylaşımı açık tercihle yönetilir; gerekirse yerel işleme yolu kullanılır.

Yedek: şifreli içerik, ayrı anahtar yönetimi, sürüm ve geri yükleme testi. Drive'daki dosyanın varlığı, modelin onu konuşmada kullanabildiğini kanıtlamaz. Silme isteği aktif hafıza/indekslerde uygulanır; yedek saklama süresi kullanıcıya açıklanır.

Önerilen kabul seti: 20 önceden yazılmış soru; farklı oturumlarda hatırlama, tarih sırası, bilgi düzeltme, proje ayrımı ve bilinmeyende cevap uydurmama. En az 18/20 doğru; yanlış kişiye/projeye veri aktarımı sıfır; silinen verinin aktif geri çağrılması sıfır. Bir sonraki gün testi ayrıca yapılır, bugünden PASS yazılmaz. Bu yaklaşım LongMemEval'in bilgi çıkarımı, çok oturum, zaman, güncelleme ve çekimserlik ayrımından yararlanır [R6].

## 9. Araç, model, hata ve güvenlik kabulü
- Model seçimi: yalnız gerçek erişilebilir model kimlikleri; metin/görsel/ses/araç yeteneği kontrolü; görev bütçesi; timeout ve tekrar limiti; test sonucuna göre seçim.
- Ses/görüntü: istenen yetenekler ayrı test edilir. Mikrofon izninin veya OCR modelinin bulunması sesli/görsel asistan uçtan uca çalışıyor kanıtı değildir.
- Araç kullanımı: açık hedef + işlem + parametre; hizmete uygun en az yetki; veri dışarı gönderme ve geri döndürülemez işlemlerde gerekli kullanıcı kararı.
- Telefon görevi: ekranı oku→planla→yetkiyi kontrol et→işlemi yap→yeniden oku→somut hedef koşulunu doğrula. Çağrının kabul edilmesi başarı değildir. AndroidWorld sistem durumuna dayalı değerlendirme için yararlı bir örnektir [R7].
- Hata öğrenimi: görev, gözlem, beklenen/gerçek sonuç, hata sınıfı, düzeltme, tekrar sayısı ve düzeltme testi. Bu otomatik model ağırlığı eğitimi olarak adlandırılmaz.
- Güvenli cihaz: kayıtlı cihaz anahtarı, geçerli kullanıcı oturumu, sunucu yetkisi ve iptal/kurtarma mekanizması. Keystore anahtar koruması sağlar; kullanıcı rolü vermez [R5].
- Audit: hassas içeriği ifşa etmeden trace ve sonucu ilişkilendir; gerektiğinde eklemeli/değişiklik saptanabilir kayıt; checkpoint ve geri yükleme.
- Normal kullanıcı izolasyonu: Owner yüzeyinin gizlenmesi yetmez; backend reddi de doğrulanır.
- Public uygulamada diğer kullanıcıları değiştirmemek regresyon testiyle ölçülür.

## 10. Çalışma ve teslim kuralları
Yeni proje/repo/temel model açılmaz. Eski Core/Bridge korunur; OWNER_ACCOUNT_PRIMARY_PATH=NO olarak yardımcı telefon-agent hattında kalır.

Önce hazır bileşen yeniden kullanılır; her değişiklik açık eksikle ilişkilendirilir. Aynı kapalı erişim koşulu her tur yeniden aranmaz; yalnız yeni kanıt veya erişim değişince tekrar kontrol edilir.

Geliştirme dalı, main, CI artifact, imzalı APK, telefonda kurulu APK ve production dağıtımı ayrı kimliklerle izlenir. Exact source HEAD ve artifact hash aynı kayıt üzerinde tutulur. Yeşil build bütünleşik çalışma değildir.

Bu rapor için GitHub'a yalnız belge kaydı amaçlanır; var olan PR24 veya main kodu değiştirilmez, merge yapılmaz. Uygulama/hesap değişiklikleri bu raporun tamamlanmasıyla gerçekleşmiş sayılmaz.

Zaman: 1–2 saatte tamamlanma taahhüdü verilmez. Önce bir dikey akış: gerçek hesap→gerçek cevap→bir hafıza yazımı→yeni oturumda doğru hatırlama→kayıt. Bunun ölçülen sonucu sonraki kapsam ve süreyi belirler.

## 11. Güncel durum, hata kaydı, karar ve devir
GUNCEL_DURUM: Public 3.2.1 binary ve Owner 1.2.0 binary bu tur karşılaştırıldı. PR24 1.3.0 kaynak ve CI durumu canlı okundu. Aynı public üründe OWNER ve tam kişisel beyin E2E kanıtlanmadı.

HATA_KAYDI: Eski raporun “hafıza/LLM yok” genellemesi artık bütün projeye uygulanamaz. Yeni kaynak ve ayrı backend çalışma kaydı vardır. Buna karşılık kaynak varlığı, imzalı release ve cihazda çalışmanın yerine geçmez.

KARAR: Mevcut hedef korunacak; kişisel hafıza ve model yolu açıkça tamamlanacak. Yeni Owner APK ana public hesap hedefinin yerine geçirilmeyecek.

DEVIR: PR24 f6cf3c08 kaynak boşlukları üzerinden entegrasyon işi tanımlanabilir. Öncelik: izinli hafıza geri çağırma + görev sonkoşulu + gerçek kullanıcı oturumu. Public ürün bağlantısı yalnız doğrulanmış yönetim/entegrasyon yüzeyinde ilerler.

SON_DOGRULANMIS_ANLIK_GORUNTU: 25 Eylül 2026; bu belgede listelenen binary hashleri, exact PR HEAD ve run numaraları. Runtime veya hesap yetkisi değişikliği yapılmış değildir.

## 12. Kaynaklar
Birincil teknik/web kaynakları, bu tur açılıp okundu:
- [R1 Google Play — Chatbot AI](https://play.google.com/store/apps/details?id=com.codespaceapps.aichat&hl=en)
- [R2 Firebase API keys](https://firebase.google.com/docs/projects/api-keys)
- [R3 Firebase App Check](https://firebase.google.com/docs/app-check)
- [R4 Firebase Remote Config](https://firebase.google.com/docs/remote-config)
- [R5 Android Keystore](https://developer.android.com/privacy-and-security/keystore)
- [R6 LongMemEval, ICLR 2025 / arXiv](https://arxiv.org/abs/2410.10813)
- [R7 AndroidWorld, araştırmacıların proje sayfası](https://google-research.github.io/android_world/)
- [R8 Firebase Custom Claims](https://firebase.google.com/docs/auth/admin/custom-claims)

Doğrudan kaynak/CI:
- [Gpt-asistan](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan)
- [PR24](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/24)
- [OwnerBrainPolicy exact HEAD](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/f6cf3c087ebee514d54a9b55d1da58d39523c91f/app/src/main/java/com/mehmetcerdik/ownerai/OwnerBrainPolicy.java)
- [OwnerMemory exact HEAD](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/f6cf3c087ebee514d54a9b55d1da58d39523c91f/app/src/main/java/com/mehmetcerdik/ownerai/OwnerMemory.java)
- [OwnerBrainEngine exact HEAD](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/f6cf3c087ebee514d54a9b55d1da58d39523c91f/app/src/main/java/com/mehmetcerdik/ownerai/OwnerBrainEngine.java)
- [Başarılı build](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/36055249746)
- [Başarısız emülatör run](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/36055244933)

Özel proje kayıtları: GUNCEL_DURUM.md (25 Eylül güncellemeleri), CURRENT_STATE (25 Eylül model çalışma eki), AUDIT_20260917_PRODUCTION_OWNER_CHAIN, PR24_8e8bb4ea yedek klasörü. İçerikleri okundu. Özel e-posta adresleri, erişim sırları ve özel dosya bağlantıları bu paylaşılabilir rapora konulmadı.
