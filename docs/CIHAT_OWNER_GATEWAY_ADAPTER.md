# CİHAT / KRAL — Yetkili model köprüsü (gerçek API gerekiyorsa)

## Ön koşul ve kanıt sınırı

Eski **CİHAT AI 3.2.1 APKM** bir model listesi, URL izleri ve uygulama motoru içeriyor; bu, programın arkasındaki hizmete bizim yönetebildiğimiz bir model API'siyle eriştiğimizi veya model ağırlıklarını elde ettiğimizi **kanıtlamaz**. Ne APK'dan gizli anahtar çıkarılır ne de hizmetin özel uç noktalarına yetkisiz erişilir.

Bu dalda sıfırdan Android asistan yazılmıyor: var olan `server.gateway.Gateway` ve `server.github_issue_bridge` korunuyor. Yeni `server.owner_gateway_provider.OwnerGatewayProvider`, **yalnız kullanıcının gerçekten yetkilendirdiği bağımsız bir HTTPS OpenAI-compatible** `/v1/chat/completions` hizmeti için adaptördür. Marka/ürün sahipliği ve CİHAT'ın özgün bulut hizmetiyle eşdeğerlik iddiası yoktur.

## İki sağlayıcıdan birini açıkça seç

- `KRAL_PROVIDER_MODE=openai`: eski mevcut `OpenAIProvider`; `OPENAI_API_KEY` ve `OPENAI_ALLOWED_MODELS` gerektirir.
- `KRAL_PROVIDER_MODE=owner_gateway`: yeni ve açıkça yetkilendirilmiş bağımsız servis; aşağıdaki tüm ayarlar gereklidir.

| Ortam değişkeni | Anlamı |
|---|---|
| `KRAL_OWNER_GATEWAY_URL` | Tam `https://<yetkili-host>/v1/chat/completions` adresi, düz port 443 |
| `KRAL_OWNER_GATEWAY_HOST` | Tam aynı DNS adı; URL ile harfiyen eşleşmeli |
| `KRAL_OWNER_GATEWAY_TOKEN` | Sağlayıcının kendi sunucu tarafı kimlik doğrulama tokenı |
| `KRAL_OWNER_GATEWAY_MODEL` | Sahibin gerçek erişim hakkı olan tek model kimliği |

**GitHub Actions için:** `KRAL_PROVIDER_MODE`, `KRAL_OWNER_GATEWAY_HOST` ve `KRAL_OWNER_GATEWAY_MODEL` değerleri repo Actions Variables; `KRAL_OWNER_GATEWAY_URL` ve `KRAL_OWNER_GATEWAY_TOKEN` değerleri yalnız Actions Secrets üzerinden alınır. Model/URL/token Issue, PR yorumu, APK veya GitHub deposuna gömülmez. Kullanıcının bizzat yetki verdiği servis hazır değilse `owner_gateway` başarısız olur; otomatik başka sağlayıcıya geçmez.

## Güvenlik ve test

- HTTPS/443, sabit path ve tam hostname eşleştirme; URL'de kullanıcı/şifre, query, fragment, yönlendirme, IP adresi ve rastgele endpoint yok.
- Çıktı boyut, tür, model kimliği ve metin doğrulaması var. Hatalarda gelen yanıta veya erişim tokenına yer verilmez. API çağrıları sadece sahibinin izin verdiği ve model probe üzerinden yanıtı doğrulanmış modele çalışır.
- Önceki Owner P-256 kimlik ve cihaz imzası kontrolleri aynen kalır. Bu adaptör kimlik yerine geçmez.
- `server/tests/test_owner_gateway_provider.py` sentetik HTTP yanıtlarıyla olumlu/olumsuz durumları sınar; **canlı CİHAT cevabı olduğunu kanıtlamaz**.
- GitHub Actions issue danışma modu ancak workflow varsayılan dalda onaylı şekilde etkinleştikten ve gerçek sağlam sağlayıcı bağlandıktan sonra cevap verebilir. PR #39 taslakken kendi başına yeni model yürütmesi oluşmaz.

## Sonraki gerçek kabul

Canlı API hakkı doğrulanmış bir kaynaktan, kesintisiz ve redacted testle `/api/v1/owner/models` ve `/api/v1/owner/chat` cevapları; model ID; önceden enroll edilmiş Owner+cihaz imzaları; gerçek GitHub run+yorum ID; ağ kapalı/yanlış token/redir/kimlik hatalarının fail-closed sonucu. Bunların yokluğunda kabul `BLOCKED` kalır.

## Eski Android bileşeni

`owner/pr27-runtime-fixes-20261002` dalındaki `CihatSemanticAdapter.java` gerçek CİHAT uygulamasına ekran/Accessibility aracılığıyla erişim için **ayrı** adaydır; yalnız cihaz sahibi onayı ve gerçek telefon testiyle kurulabilir. Bu HTTPS adaptörüyle aynı mekanizma değildir ve ikisi tamamlandı diye gösterilemez.
