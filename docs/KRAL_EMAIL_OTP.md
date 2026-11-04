# E-posta OTP girişi

- Uç noktalar (imzasız, giriş öncesi): `POST /api/v1/owner/email-otp/request` ve `/verify` (`server/email_otp.py`).
- Kod yalnız `KRAL_OTP_OWNER_EMAIL` adresine gider (varsayılan `mehmetcerdik457@gmail.com`); istemci başka adres veremez.
- 6 haneli kod, 10 dk geçerli, tek kullanımlık, challenge başına 5 deneme, 10 dk'da en fazla 3 istek. Kod yalnız HMAC özeti olarak saklanır.
- SMTP ayarları yalnız ortam değişkenlerinden okunur: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SSL`; `KRAL_OTP_SECRET` ayarlanmalıdır (bkz. `server/config.env.example`). SMTP yoksa istek `503` ile kapalı başarısız olur.
- Android: varsayılan e-posta `EmailOtp.DEFAULT_EMAIL`; kilit ekranındaki alandan değiştirilebilir.
- OTP yalnız uygulama kilidini açar; imzalı sahip/cihaz API'lerinin yetkisini değiştirmez.
