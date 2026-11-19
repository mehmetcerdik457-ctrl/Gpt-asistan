# KRAL / OMEGA — motor ve araç envanteri (22 Ekim 2026)

Bu envanter **kaynak kanıtı** ile **canlı erişim kanıtını** ayrı tutar. Depoda
bir adaptör veya APK bulunması, anahtarın geçerli, modelin yetkili veya servisin
çalışır olduğunu kanıtlamaz. Bu çalışma sırasında hiçbir sağlayıcıya istek
gönderilmedi; tüm `live_tested` alanları false kalır.

## Erişim sınıfları

- **Kod mevcut:** kaynakta istemci/adaptör var.
- **Yapılandırma göstergesi:** yalnızca gerekli env alanlarının boş olmadığını
  ifade eder; token değeri gösterilmez ve bu bir bağlantı testi değildir.
- **Canlı doğrulandı:** yalnızca yetkili gerçek çağrıdan model ID ve redakte
  edilmiş sonuç kanıtı geldiğinde kullanılabilir. Bu denetimde hiçbir motor bu
  sınıfta değildir.

## Motor adayları

| Aday | Kaynak kanıtı | Şu anki sınıf | Canlı test | Engel |
|---|---|---|---|---|
| OpenAI Responses API | [Gpt-asistan/server/gateway.py](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/integration/kral-asistan-20261020/server/gateway.py) | Sunucu adaptörü mevcut | Hayır | API key/model allowlist ve canlı çağrı doğrulanmadı |
| Android OpenAI-compatible HTTPS | [ModelGateway.kt](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/integration/kral-asistan-20261020/app/src/main/java/com/example/gptasistan/ModelGateway.kt) | İstemci mevcut; endpoint elle yapılandırılır | Hayır | Cihaz konfigürasyonu/sağlayıcı erişimi CI'da yok |
| Owner Gateway | [owner_gateway_provider.py](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/integration/cihat-github-task-bridge-20261021/server/owner_gateway_provider.py) | Ayrı entegrasyon dalında adaptör | Hayır | Yetkili URL, token ve model erişimi kanıtlanmadı |
| OMEGA/OpenAI | [benim-uygulamam/backend/server.py](https://github.com/mehmetcerdik457-ctrl/benim-uygulamam/blob/main/backend/server.py), [OMEGA Phase 0](https://github.com/mehmetcerdik457-ctrl/benim-uygulamam/blob/main/docs/PROJECT_OMEGA_PHASE_0.md) | OpenAI yapılandırılırsa çağrı yapabilen backend | Hayır | Yerel runtime yok; sağlayıcı provision edilmemiş |
| OpenAI Agents SDK | [openai-agents-python](https://github.com/mehmetcerdik457-ctrl/openai-agents-python) | Ajan çerçevesi / SDK kaynağı | Hayır | SDK motor/kimlik bilgisi değildir; gerçek task run kanıtı yok |
| Eski CİHAT/GPTMobile APK | [telefon-yedek](https://github.com/mehmetcerdik457-ctrl/telefon-yedek) | APK artefaktı | Hayır | APK içeriği ve arka uç bu görevde incelenmedi |
| rish-mcp | [README](https://github.com/mehmetcerdik457-ctrl/rish-mcp/blob/master/README.md) | Android shell/MCP köprüsü; model değil | Hayır | Relay, cihaz eşlemesi ve bağlı AI istemcisi doğrulanmadı |
| Google Gemini / Vertex | İncelenen depolarda doğrulanmış uygulama izi bulunamadı | Kanıtsız aday | Hayır | Kod/config ve yetkili endpoint yok |
| Ollama / yerel modeller | OMEGA Phase 0 yerel runtime olmadığını belgeliyor | Kanıtsız aday | Hayır | Bu GitHub oturumuna sahibin makinesi/model sunucusu bağlı değil |
| ZTN GPT | Erişilebilir depolarda doğrulanmış eşleşme bulunamadı | Kanıtsız aday | Hayır | Bulunabilir repo/artefakt veya yetkili endpoint gerekli |

## Hesap genelinde taranan 19 depo

`Gpt-asistan`, `.github`, `mehmetcerdik457-ctrl`, `repo-template`,
`studio`, `doktor`, `hata-ayiklayici`, `termux-mods`, `apk-starter`,
`bot-starter`, `serverless-starter`, `benim-uygulamam`, `Magisk`,
`telefon-yedek`, `Shizuku`, `codespaces-react`, `openai-agents-python`,
`docs`, `rish-mcp`.

İlk README/tree taramasında küçük starter depoları genel şablon veya boş kaynak
iskeleti; Magisk ve Shizuku telefon/izin altyapısı; Codespaces React genel UI
iskeleti olarak görünüyor. Bunlar kendi başlarına model motoru sayılmadı.

## Gerçek GitHub görev köprüsü durumu

[PR #39](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/39)
dalındaki `server/github_issue_bridge.py` yalnızca:
1. sabit test komutunu çalıştıran CI kanıtı veya
2. açıkça etkinleştirilmiş sağlayıcı varsa salt-danışma model yanıtı

üretebilir. Issue içeriğini kod olarak çalıştırmaz ve kendi başına kaynak
dosyalarını değiştiren bir coding agent değildir. `cihat-task` etiketli
[Issue #45](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/issues/45)
açıldı; bu oturumda issue-event workflow sonucu/model yanıtı henüz görünmedi.
Bu yüzden modelin görevi yürüttüğü iddia edilmez. Workflow yalnızca entegrasyon
dalında bulunduğundan varsayılan dalı değiştirmeden otomatik model görevi
garanti edilemez.

## Güvenli sonraki geliştirme

`server/motor_inventory.py` sadece katalog kanıtlarını ve env varlarının
var/yok durumunu raporlar; secret değerlerini dışarı çıkarmaz, ağ isteği
yapmaz ve `live_tested=true` üretmez. Testler sentetik env ile bu sınırları
doğrular. Gerçek model testi ancak mevcut yetkili sağlayıcıya onaylı, küçük
bir probe gönderilip dönen gerçek model ID ve redakte edilmiş sonuç kaydedilince
ayrı bir kanıt olarak eklenmelidir.
