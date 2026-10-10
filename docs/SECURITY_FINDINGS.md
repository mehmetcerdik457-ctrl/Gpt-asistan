# Security findings
- Yalnızca bu repoda desen taraması yapıldı (`scripts/validate_structure.sh`): sabit gömülü sır **bulunmadı**.
- Anahtar rotasyonu gerekli: bulunmadı. Başka repolar taranırsa bulgular buraya yalnızca dosya yolu/satır ile eklenmeli.
- `.env` `.gitignore`'dadır; `.env.example` yalnızca boş değişken adları içerir.
- Drive kimlik bilgileri yalnızca GitHub Secrets (`GDRIVE_SERVICE_ACCOUNT_JSON`, `GDRIVE_FOLDER_ID`) ile verilir.
- Not: önceki PR'larda (#33, #34 vb.) sır olup olmadığı bu çalışmada incelenmedi.
