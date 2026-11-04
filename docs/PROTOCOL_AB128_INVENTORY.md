# Protokol A/B-128: teknik envanter ve açık kabul kapıları

Bu belge, 2026-11-03 tarihinde erişilebilen kaynakların bir anlık görüntüsüdür.
Bir şartnameyi veya test sonucunu kaynak kanıt olmadan tamamlanmış saymaz.
İki depo için ayrı kaynak ve kabul durumları korunur.

## Kaynaklar ve sınırlar

| Kaynak | Kanıtlanan durum |
| --- | --- |
| [KRAL](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan) | Genel depo; `main` gözlem SHA'sı `5062b22ccfc11bdd10302bed75e5902deeb4ea4c`. Bu belge #88'in `b87b1c538be5c777b52ac5e64db2d384e3e18860` kaynak ağacı üzerine hazırlanmıştır; `main` değildir. |
| [OMEGA](https://github.com/mehmetcerdik457-ctrl/benim-uygulamam) | Ayrı genel depo; `main` gözlem SHA'sı `f410e09466026a19fb47193f70d25d3c5f8544a5`. |
| KRAL Genesis 3.0 PDF | Bu çalışma alanında belirtilen adla bulunamadı; ChatGPT dosya kütüphanesine veya Drive'a erişim doğrulanmadı. 28 bölüm ve T01–T26 için şartnameye dayalı tam eşleme yapılamaz. |
| [KRAL profil PR #84](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/84) | 12 profil dosyası içerir. Profil dosyası, canlı bir Copilot oturumu veya yetki kabulü kanıtı değildir. |
| [KRAL Android PR #86](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/86) | Kaynak `276f84109cb32826416d63b8b4d18bb702190f3c`; imzalı debug adayının eski APK üzerine veri koruyarak kurulması doğrulanmamıştır. |
| [KRAL imzalama PR #88](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/88) | #86 üzerinde bir commit; kaynak `b87b1c538be5c777b52ac5e64db2d384e3e18860`. Owner secrets işe sağlanmadığından owner imzası engellidir; APK debug adayıdır. |

## GitHub iş envanteri

GitHub API sorgularının anlık sonucu: KRAL'da 118 dal, 65 açık PR ve
13 açık issue; OMEGA'da 91 dal, 58 açık PR ve 26 açık issue. Sayımlar
değişebilir; başlık benzerliği tek başına işlerin eşdeğer olduğunu göstermez.
Hiçbir dal, PR veya dosya silinmemiştir.

KRAL kaynak bağımlılığı #82 → #83 → #84 → #85 → #86 → #88 şeklindedir.
[#87](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/87), #86
kaynak ağacının `main` için ayrı taslak inceleme yüzeyidir; #88'i içermez.
`fix/kral-voice-cihat-review-20261103` dalındaki `29e011b3123a5265bdcdba21613fe8f279d0b8f9`,
#88'den iki commit ileride ve bir commit geridedir: dallar ayrışmıştır.
Değişiklikler otomatik birleştirilmemelidir.

İlişkili, ancak otomatik olarak yinelenen sayılmayan işler:

- KRAL [#40](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/issues/40),
  [#41](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/issues/41),
  [#43](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/issues/43),
  [#54](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/issues/54) ve
  [#61](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/issues/61):
  görev kuyruğu, bağımsız CI veya uzman çalıştırma kanıtı.
- OMEGA [#20](https://github.com/mehmetcerdik457-ctrl/benim-uygulamam/issues/20)
  ve [#25](https://github.com/mehmetcerdik457-ctrl/benim-uygulamam/issues/25):
  Faz 0 ve gereksinim matrisi; [#80](https://github.com/mehmetcerdik457-ctrl/benim-uygulamam/issues/80):
  uzman görevlendirme ve kanıt kapısı;
  [#56](https://github.com/mehmetcerdik457-ctrl/benim-uygulamam/issues/56):
  şifreli yedekleme/geri yükleme kabul engeli.

## Kod ve profil envanteri

KRAL `main`, Genesis dallarıyla aynı kaynak ağacı değildir. `main` içindeki
[Python CI](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/5062b22ccfc11bdd10302bed75e5902deeb4ea4c/.github/workflows/ci.yml)
Python sürümünü yazdırır; #88'in Python test kanıtı `main` testi olarak
sunulamaz. #88 ağacında Android ve Gradle kaynakları, `server/`, Android JVM ve
cihaz testleri, Python testleri ve `.github/agents/` bulunur. Kodun varlığı,
şartname kabulünün kanıtı değildir.

[#84 profil kurtarma belgesi](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/blob/74ff9ef3930b0bc3a0fbbccb4bfe3dd91a5a00f6/docs/KRAL_AGENT_ROLE_RECOVERY.md)
12 profil ile çalışan ajanların farklı şeyler olduğunu belirtir. Aşağıdaki
eşleme plan niteliğindedir; profil yetkisi, çalışma zamanı ve bağımsız yürütme
bu envanterde doğrulanmamıştır. Yetkinin veya rol kapsamının belirsiz olduğu
yerde yeni ajan oluşturulmamıştır.

| İş kimliği ve sorumluluk | Mevcut profil adayı | Doğrulama veya sınır |
| --- | --- | --- |
| AB128-01 koordinasyon | `chief-engineer` | Dağıtım ve entegrasyon; tek yazarlı koordinasyon gerekir. |
| AB128-02 Android | `android-engineer` | `app/`, Kotlin ve Gradle. |
| AB128-03 backend | `cloud-engineer` | Backend/Python kapsamı ve yazma yetkisi ayrıca doğrulanmalı. |
| AB128-04 modeller | `ai-ml-engineer` | Model yönlendirme ve Responses API kapsamı ayrıca doğrulanmalı. |
| AB128-05 güvenlik | `security-auditor` | Profil salt okunur denetçidir; güvenlik kodu yazma yetkisi varsayılmaz. |
| AB128-06 veri | `ai-ml-engineer` | Hafıza ilgili olsa da SQLCipher, yedekleme ve yazma yetkisi doğrulanmadı. |
| AB128-07 DevOps | `ci-cd-engineer` | İş akışları ve derleme kanıtı. |
| AB128-08 test | `test-engineer` | Test ve regresyon; cihaz ve sağlayıcı erişimi ayrı kapıdır. |
| AB128-09 APK | `apk-forensic`, `release-engineer` | İnceleme ve sürüm kanıtı; owner imzasına erişim varsayılmaz. |
| AB128-10 yetenek | `mcp-engineer` | Araç entegrasyonu adayı; 13 aşama kapsamı doğrulanmadı. |
| AB128-11 OMEGA | Eşleşme doğrulanmadı | OMEGA şartnamesi ve ayrı depo çalışma yetkisiyle değerlendirilmeli. |
| AB128-12 bağımsız denetim | `code-reviewer` | Salt okunur; kendi ürettiği işi bağımsız kabul etmez. |

`github-master-ai` genel GitHub koordinasyonu için mevcut profildir; yönetim
yetkisi veya aktif yürütme kanıtı değildir. Gerçek iş dağıtımından önce her
işe ayrı dal/çalışma alanı, dosya sahipliği, test ve teslim ölçütü atanmalı;
ortak dosyalardaki yazılar tek koordinatör tarafından seri hale getirilmelidir.
Yukarıdaki kimlikler çalışan, kalıcı görev kuyruğu olarak yorumlanmamalıdır.

## Doğrulanmış CI ve cihaz sınırları

- #88 kaynak commit'i için [Python CI](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41651717856)
  ve [Android build/API 30/API 36](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41651708048)
  başarılıdır. #88 raporu 121 Python testi, 75 başarılı ve 6 atlanan JVM testi,
  emülatör başına 16 Android testi bildirir. JVM atlamaları JVM başarısı değildir.
- #88'in APK artefaktı
  [buradadır](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/actions/runs/41651708048/artifacts/13237831848);
  bildirilen APK SHA-256:
  `4808a7fbc47d31615419e152cf85536e7b0f623f439fd4feb5595d19dffa8cfd`.
  Bu dosya owner imzalı nihai APK veya mevcut kurulum üzerine güvenli güncelleme olarak kabul edilmez.
- Fiziksel cihaz, biyometri, mikrofon/hoparlör, gerçek CİHAT ve canlı ücretli
  model erişimi için bu CI sonucundan kabul çıkarılamaz. Mevcut uygulamayı
  kaldırmak veya verisini silmek güvenli güncelleme yerine geçmez.
- Actions izinleri, faturalama kotası ve GitHub secret-scanning uyarıları için
  API sorguları `403 Resource not accessible by integration` döndürdü. Başarılı
  geçmiş koşular, gelecekteki kota veya yürütme yetkisini kanıtlamaz.
- Her iki depo genel olduğundan Copilot cloud automation oluşturma yolu bu
  ortamda uygun değildir. Kalıcı kuyruk veya otomatik yeniden başlatma bu
  envanter tarafından kurulmuş ya da çalışıyor olarak gösterilmez.

## Kabul ve yetki kapıları

KRAL 28 bölüm / T01–T26, OMEGA 100 madde, owner imzası, mevcut kurulum üzerine
veri koruyan güncelleme, gerçek cihaz ve yetki yalıtımlı canlı uzman çalıştırma
ayrı kanıt gerektirir. Bunlar tamamlanmadan %100 kabul veya nihai APK iddiası
yapılmaz. Ücret, sır aktarımı, hesap izinleri, üretime dağıtım, geri alınamaz
veri değişikliği ve `main` birleşimi açık sahip onayı gerektirir.
