# E-posta OTP girişi

- Uç noktalar (imzasız, giriş öncesi): `POST /api/v1/owner/email-otp/request` ve `/verify` (`server/email_otp.py`).
- Kod yalnız `KRAL_OTP_OWNER_EMAIL` adresine gider (değer sunucu ortamında zorunludur; varsayılan e-posta yoktur); istemci başka adres veremez.
- 6 haneli kod, 10 dk geçerli, tek kullanımlık, challenge başına 5 deneme, 10 dk'da en fazla 3 istek. Kod yalnız HMAC özeti olarak saklanır.
- SMTP ayarları yalnız ortam değişkenlerinden okunur: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SSL`; `KRAL_OTP_SECRET` kalıcı, rastgele ve en az 32 bayt olmalıdır; aynı veritabanını kullanan gateway işçileri aynı sırrı kullanmalıdır (bkz. `server/config.env.example`). SMTP ayarları veya yeterli kalıcı sır yoksa gerçek gönderim isteği `503` ile kapalı başarısız olur. `SMTP_FROM` boşsa `SMTP_USER` gönderen adresi olarak kullanılır.
- Android: herkese açık APK içinde sahip e-postası bulunmaz; kilit ekranında kullanıcı tarafından girilir ve cihazda saklanır.
- OTP başarısı e-posta adımını tamamlar; kişisel kayıtları açmadan önce Android'in güvenli cihaz ekran kilidi ayrıca doğrulanır. Güvenli cihaz kilidi yoksa kayıtlar açılmaz. Düzenlenebilir HTTPS adresinden dönen `verified: true` cihaz doğrulamasının yerine geçmez.
- E-posta sunucusu `otp_endpoint` tercihinde tutulur; kilit ekranındaki form imzalı model bağlantısının `endpoint` ayarını değiştirmez. HTTPS adresi kullanıcı tarafından girilir; uygulama bu adresi sabit bir güven piniyle doğruladığını iddia etmez.
- Uygulama arka plana geçtiğinde bekleyen OTP sonuçları geçersiz sayılır ve açık diyaloglar kapatılır. Yeniden deneme kullanıcı tarafından başlatılır; otomatik kod isteği veya sağlayıcı çağrısı yapılmaz.
- OTP imzalı sahip/cihaz API'lerinin yetkisini değiştirmez. Sunucuda canlı SMTP gönderimi ve gerçek telefonda giriş ayrı kabul kanıtı gerektirir.

- Güvenlik/göç notu: Eski commitlerde yayımlanmış bir e-posta adresini yeni koddan kaldırmak Git geçmişini silmez. Geçmiş kaynakları silme, zorla yeniden yazma veya eski cihazı kaldırma yapılmaz.
