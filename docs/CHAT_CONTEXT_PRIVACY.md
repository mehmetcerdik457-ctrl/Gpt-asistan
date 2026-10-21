# Sohbet bağlamı ve paylaşım denetimi

Kral Asistan, sohbet geçmişini yerel SQLCipher veritabanında saklar. Model isteği, kullanıcı ayrıca paylaşım anahtarını açmadıkça yalnızca o an yazılan iletiyi gönderir. `Önceki model sohbetlerini paylaş` anahtarı varsayılan olarak kapalıdır; tercih cihazın uygulama ayarlarında saklanır ve her istekte açıkça `include_history` olarak iletilir.

Anahtar açık olduğunda OMEGA gateway, yalnızca kayıtlı önceki model sohbetlerinden en yeni üç soru/yanıt çiftini kronolojik sırayla, toplam 12.000 karakter üst sınırıyla sağlayıcıya verir. Bu sınır aşılırsa bağlam, en yeni çift korunarak kırpılır. Kullanıcının cihazda tuttuğu yerel `/kaydet`, görev ve yerel komut kayıtları bu mekanizmayla gönderilmez. Mevcut Android istemcisi `include_memory` değerini kapalı gönderir; bu değişiklik sunucu hafızasını açmaz.

Gateway geçmişi sağlayıcıya iletmeden önce çift imzalı sahip/cihaz kimlik doğrulamasını, doğrulanmış model kaydını ve istek limitlerini uygular. Sunucu, soru ve yanıtları kalıcı sohbet tablosunda saklar; bu yeni anahtar yalnızca önceki kayıtların sağlayıcı istemine eklenmesini denetler. Kullanıcı paylaşım anahtarını kapalı tuttuğunda sağlayıcı çağrısı geçmiş içeriğini almaz.

Bu belge, bu kod davranışını ve regresyon testlerini açıklar; geçerli sağlayıcı anahtarı, çalışan/deploy edilmiş OMEGA sunucusu, gerçek kullanıcı hesabı veya fiziksel telefonda uçtan uca çalışma kanıtı değildir. Canlı sağlayıcıya giden geçmiş paylaşımı, yalnız uygulama kullanıcı tarafından güvenilir bir HTTPS OMEGA endpoint'ine bağlanıp anahtar açıldıktan sonra gerçekleşir.
