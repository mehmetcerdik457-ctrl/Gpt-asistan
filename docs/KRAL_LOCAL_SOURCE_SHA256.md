# KRAL GENESIS — Android yerel dosya SHA-256 denetimi (taslak)

Bu değişiklik PR #52 üzerine eklenmiştir ve mevcut Owner imzalı sunucu incelemesini veya orijinal APK'ları değiştirmez.

## Kullanım

1. KRAL önizlemesini cihaz kilidiyle aç.
2. "Telefondan dosya seç ve SHA-256 hesapla (çevrimdışı)" düğmesine dokun.
3. Android sistem dosya seçicisinden tek bir belge seç.
4. Cihaz kimlik doğrulamasını tekrar yap.
5. KRAL yalnızca seçili dosyayı 128 MiB sınırıyla okuyup adı, bayt sayısı ve SHA-256 özetini gösterir.

Dosya URI'si kalıcı olarak saklanmaz. Dosya sunucuya ya da yapay zekaya gönderilmez. Sohbet veya kalıcı hafıza yazılmaz; APK yüklenmez ve çalıştırılmaz. Kaynak değiştirilmez.

Bu sonuç APK imzası, lisans, sahiplik, kurulum başarısı, canlı model ya da üretim Owner kimliği kanıtı **değildir**.

## Kabul kapıları

Android JVM testleri, lint, APK derlemesi ve emülatör iş akışı tam commit SHA üzerinde doğrulanmalıdır. Gerçek telefon dosya seçimi, haricî SHA ile çapraz doğrulama, APK imzası ve Owner HTTPS/model uçtan uca kanıtı ayrı olarak beklemededir. Test edilmeyeni PASS olarak raporlama.

main'e merge yapma; eski APK'ları silme; gizli anahtarları isteme veya yazma.
