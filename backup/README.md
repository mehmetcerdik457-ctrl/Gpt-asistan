# Google Drive backup

Credentials are **never** stored in this repo. Provide them via environment variables / GitHub Secrets.

## Python (Drive API)
```
pip install -r backup/requirements.txt
export GDRIVE_FOLDER_ID=...                 # target folder (share with the service account)
export GDRIVE_SERVICE_ACCOUNT_JSON="$(cat key.json)"   # or GDRIVE_OAUTH_TOKEN_JSON
python backup/backup_to_drive.py evidence/out
```

## rclone
Configure a remote first (`rclone config`), then `backup/backup_to_drive.sh . gdrive:Gpt-asistan-backup`.

## Evidence
`python evidence/generate_evidence.py` writes logs and copies of the INVENTORY / MIGRATION_REPORT
docs into `evidence/out/`; that directory is zipped and uploaded by the workflow
`.github/workflows/backup-drive.yml` (manual `workflow_dispatch`).

Required GitHub Secrets: `GDRIVE_SERVICE_ACCOUNT_JSON`, `GDRIVE_FOLDER_ID`.
This was not executed against a real Drive account in development.
