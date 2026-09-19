# MEHMET YARATILIŞ v0.2.2 — Telefon Çalışma Adayı

## Amaç
Bu paket v0.2.0 ara sürümünden türetilmiştir. v0.2.0 değiştirilmemiştir.

## HTTPS gereksinimi
Kamera, mikrofon, service worker ve PWA kurulumu için telefonda güvenilir HTTPS origin kullanın. Düz `file://` açılışı tam PWA testi değildir.

## Statik HTTPS yayın
Kök dosya `index.html`dır; `MEHMET.html` aynı UI girişidir. Statik host tüm dosyaları aynı dizin yapısıyla servis etmelidir. Provider/araştırma bridge'i aynı origin'de yoksa uygulama bunu açıkça UNCONFIGURED/BLOCKED gösterir ve sahte sonuç üretmez.

## Güvenli köprü
Yerel test: `python3 bridge/MEHMET_GUVENLI_KOPRU.py`. TLS sertifika/anahtarınız varsa `MEHMET_TLS_CERT` ve `MEHMET_TLS_KEY` ortam değişkenleriyle HTTPS açılabilir. Ham API anahtarlarını HTML/JS'ye koymayın.

## Telefon kabul testi
1. HTTPS URL'yi açın; Ayarlar > Çalışma Zamanı `secureContext=PASS` göstermeli.
2. PWA'yı ana ekrana kurun.
3. Bir mesaj gönderin; provider yoksa sistem sahte model yanıtı üretmemeli.
4. Tarayıcı/PWA'yı tamamen kapatıp açın; sohbet geçmişi geri gelmeli ve Hafıza panelindeki yeniden açılış kanıtı PASS olmalı.
5. Dosya seçin; SHA-256 görüntülenmeli.
6. Kamerayı açın ve fotoğraf yakalayın.
7. Mikrofonu başlatıp durdurun; sıfırdan büyük ses dosyası oluşmalı.
8. Ses düğmesiyle son mesajın okunmasını tamamlayın.
9. Dil değiştirin; temel gezinme, düğmeler ve alanlar gerçekten değişmeli.
10. Bir kez çevrimiçi açtıktan sonra ağı kapatıp PWA'yı yeniden açın; kabuk açılmalı.
11. Görev Geçmişi ve Hata Kaydı gerçek olayları göstermeli.
