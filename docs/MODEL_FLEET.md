# Kral model ekibi

`./kral-ai --fleet` yapılandırılan metin modellerini bir ekip olarak çalıştırır:
isteğe uygun uzmanları seçer, görüşleri paralel toplar, bir koordinatörle birleştirir.
Koordinatör erişilemezse yapılandırılmış sıradaki koordinatörü dener. Bu bir metin
orkestrasyonudur; işletim sistemi komutu, MCP aracı, dağıtım veya model indirme çalıştırmaz.

## Kurulum

1. Kendi bilgisayarında veya sunucunda bir Chat Completions uyumlu sunucu çalıştır.
   Ollama ve vLLM bu protokolü sunar. Modelin lisansı, bellek gereksinimleri,
   sunucudaki tam model kimliği ve desteklenen parametreler ayrıca doğrulanmalıdır.
2. `kral/safe/fleet.example.json` dosyasını özel yapılandırma dizinine kopyala.
   `REPLACE_WITH_...` yer tutucularını gerçekten kurulu model kimlikleriyle değiştir.
   Örnek dosya kurulu veya test edilmiş gerçek model listesi değildir.
3. `base_url` adresini sunucuna ayarla. `/v1` dahil edilir; `/chat/completions` eklenmez.
   HTTPS zorunludur; yalnız localhost, 127.0.0.1 ve ::1 için HTTP kabul edilir.
   Yerel adres, **asistanın çalıştığı makineyi** belirtir; bulut ortamından telefonuna erişmez.
4. Uzak sunucu anahtar istiyorsa model kaydına `"api_key_env": "MY_MODEL_TOKEN"` ekle.
   Anahtarı yalnız bu ortam değişkenine secret yöneticisi üzerinden bağla.
   JSON içine anahtar değeri yazma. Yapılandırma güvenilir yerel yönetici girdisidir;
   her seçilen sunucu görev metnini, koordinatörler ise uzman görüşlerini de alır.

```bash
export KRAL_FLEET_CONFIG="$HOME/.config/kral/fleet.json"
./kral-ai --models
./kral-ai --probe-models
./kral-ai --fleet "Bu tasarımı incele ve eksiklerini açıkla" --task code
```

`--models` ağ çağrısı yapmaz. `--probe-models`, sunucunun `/models` listesini kontrol
eder; `listed` cevabı inference, çıktı kalitesi veya lisans doğrulaması değildir.
Gerçek inference denemesi `--fleet` ile yapılır ve barındırılan hizmetlerde ücret doğurabilir.
Hiçbir ücretsiz kullanım veya model erişimi varsayılmaz.

## Yönetim ve sınırlar

- Liste en fazla 64 yapılandırılmış model içerebilir. Her modelin `tasks` alanı
  `general`, `code`, `research`, `writing` görevlerinden hangilerini üstlendiğini belirtir.
- Göreve uyan ilk `max_specialists` model seçilir. Sıra yöneticinin önceliğidir;
  kalite sıralaması veya otomatik benchmark sonucu değildir.
- `max_specialists`: varsayılan 3, en fazla 8; `max_parallel`: varsayılan 2, en fazla 4.
- `coordinators`: sıralı yedekler, en fazla 3. Bir görevde en fazla
  `max_specialists + koordinatör sayısı` inference çağrısı yapılır. Gizli tekrar yoktur.
- `max_output_tokens`: çağrı başına 64–8000. Sunucunun desteklemediği parametre
  açık hata üretir. Token sınırında kesilen cevap başarılı sayılmaz.
- `timeout_seconds`: 1–180 saniye ağ işlemi zaman aşımı; tüm görevin duvar saati
  süresi değildir. Görev süresi uzman grupları ve koordinatör denemeleriyle uzayabilir.
- Girdi, cevap karakter sayısı ve HTTP cevap boyutu sınırlıdır. HTTP yönlendirmeleri
  kapalıdır; sunucu hata gövdeleri ve anahtarlar hata kaydına kopyalanmaz.
- Model görüşleri talimat olarak değil, birleştirme girdisi olarak sunulur. Bunun
  modelin her zaman doğru davranacağını garanti ettiği iddia edilmez.
- Görev başına çıktı JSON'dur: cevap, model/evre, süre, hata kodu ve çıktı SHA-256.
  Hash içerik bütünlüğü içindir; cevabın doğruluğunu kanıtlamaz.
- `success` / çıkış 0: tüm seçilen çağrılar yanıt verdi. `partial` / çıkış 3:
  hata olan çağrılar var, koordinatör yanıt verdi. `failed` / çıkış 2: nihai yanıt yok.
  Bu durumlar **model yanıtı alınmasını** gösterir, içerik doğruluğu testi değildir.
- Bu mod eski sohbet hafızasını dış sağlayıcılara göndermez ve yeni cevapları
  otomatik kalıcılaştırmaz. Çıktı JSON'unu saklarsan görev/cevap gizliliğini koru.

## Doğrulama

```bash
python -m unittest discover -s kral/safe -p 'test_*.py' -v
python -m unittest discover -s kral/mcp -p 'test_*.py' -v
python .github/scripts/validate_platform.py
```

`test_fleet.py` yönlendirme, paralellik, sınırlar, kısmi hata, koordinatör yedeği,
bozuk cevaplar, anahtar yokluğu ve gerçek loopback HTTP üzerinden CLI protokolünü
kontrol eder. Loopback sunucusu test fikstürüdür; gerçek model sunucusu değildir.
CI bu testleri mevcut `CI / test` işi içinde keşfeder.

Bu değişiklik model ağırlığı indirmez, GPU kiralamaz, lisans kabul etmez ve canlı
sunucu kurmaz. Üretimde hazır sayılması için yapılandırılmış gerçek model sunucularında
inference ve kullanıcıya uygun kalite testleri ayrıca yapılmalıdır.

Protokol kaynakları:
- https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx
- https://docs.vllm.ai/en/v0.31.0/serving/online_serving/openai_compatible_server/
