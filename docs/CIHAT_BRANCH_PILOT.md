# KRAL Branch Task Queue — tekrar kullanılabilir sabit CI görevi

Bu akış **Issue #40 tek-seferlik pilotundan** farklı olarak gelecekteki owner kaynaklı başka `[KRAL-CHECK]` Issue numaralarını destekler. Android APK kaynakları bozulmaz ve `main` dalı değiştirilmez.

### İşleyiş

1. Kullanıcı/ChatGPT Github bağlayıcısı üzerinden `[KRAL-CHECK] ...` başlıklı Issue oluşturur. İçine sır/kimlik bilgisi yazılmaz.
2. Yalnız entegrasyon dalındaki `server/task_ticket.json` dosyası tam `{"schema":1,"repository":"mehmetcerdik457-ctrl/Gpt-asistan","operation":"fixed_ci","issue_number":41}` yapısında **seçilen Issue** numarasıyla güncellenir.
3. Bu dosyadaki push, `.github/workflows/kral-branch-pilot.yml` iş akışını tetikler. GitHub repo, actor, dal ve event; dosyanın tam şeması; canlı Issue'da açık + depo sahibi yazar + `[KRAL-CHECK] ` başlığı yeniden doğrulanır.
4. **Issue gövdesi komut/model promptu değildir.** Yalnız sabit `python -m unittest discover -s server/tests -v` testleri çalışır. Başarı varsa Actions run, SHA ve test sayısını içeren bot yorumu seçilen Issue'ya eklenir.
5. Aynı Issue daha önce botun başarısını aldıysa yeni yanıta izin verilmez. Bir sonraki görev için **yeni Issue numarası** seçilir.

**Kabul kanıtı:** Issue #40 [ilk pilot](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/issues/40#issuecomment-6322955982) 61 PASS. Issue #41 [ikinci görev](https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/issues/41) çoklu Issue akışını doğrulamak içindir.

**Güven sınırı:** Bu, kaynak kodu test edip sonuç gönderen GitHub robotudur. CİHAT 3.2.1'in canlı yapay zekâ modeli değildir; telefona erişmez, koda otomatik patch yapmaz, kimlik/Owner imza sistemini atlamaz. Yetkili canlı model bağlantısı ve cihaz kabulü ayrıca gereklidir. Normal `issues` workflow'u `main`de onaysız etkinleştirilmez.

**Kısıt:** Entegrasyon dalındaki task ticket push'u gerektiğinden, yalnız Issue açmak otomasyonu başlatmaz. Bunu burada görev + GitHub branch yazma izniyle yapabiliyoruz. Bu evrede otomatik push yetkisi sürekli bir servis değildir.
