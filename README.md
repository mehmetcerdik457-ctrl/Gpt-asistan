# Gpt-asistan (monorepo)

## Dizin yapısı
```
app/, kral/        Ana proje (Android kabuğu + Python asistan)
projects/<ad>/     Alt projeler (termux-mods, benim-uygulamam, studio, doktor,
                   hata-ayiklayici, telefon-yedek, serverless-starter, bot-starter,
                   apk-starter, repo-template, codespaces-react, github-config)
archive/           Çakışma çözümünde taşınan dosyalar
backup/            Google Drive yedekleme (Python + rclone)
scripts/           Doğrulama scriptleri
MANIFEST.md        Dahil/hariç projeler ve bağlantılar
```
Alt proje içerikleri şu an yer tutucudur; her birinin README'sinde import komutu vardır (`git subtree add`, geçmişi korur). Harici projeler (Magisk, Shizuku, openai-agents-python, rish-mcp, docs) kopyalanmadı; bkz. [MANIFEST.md](MANIFEST.md).

## Geliştirme
- Android: `./gradlew assembleDebug`
- Python asistan: `python kral/safe/assistant.py`

## Yedekleme
Bkz. [backup/README.md](backup/README.md).

## Doğrulama
```bash
./scripts/validate_structure.sh
```
