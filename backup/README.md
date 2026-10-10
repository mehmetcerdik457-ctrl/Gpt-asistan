# Google Drive yedekleme

Kimlik bilgileri repoya gömülmez; yalnızca env/secret ile verilir.

## Python (Drive API)
1. Google Cloud'da servis hesabı oluşturup Drive API'yi etkinleştirin, JSON anahtarı indirin.
2. Drive'da hedef klasörü servis hesabı e-postasıyla paylaşın (Editor).
3. Çalıştırın:
```bash
pip install -r backup/requirements.txt
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat sa.json)"   # veya dosya yolu
export DRIVE_FOLDER_ID="<klasör-id>"
python backup/backup_to_drive.py
```

## rclone
```bash
rclone config            # "gdrive" adlı bir drive remote oluşturun
export RCLONE_REMOTE=gdrive DRIVE_PATH=gpt-asistan-backup
./backup/backup_to_drive.sh
```
CI için `RCLONE_CONFIG_GDRIVE_*` env değişkenleri kullanılabilir.

## GitHub Actions
`.github/workflows/backup-drive.yml` manuel tetiklenir. Gerekli secret'lar:
`GOOGLE_SERVICE_ACCOUNT_JSON`, `DRIVE_FOLDER_ID`.
