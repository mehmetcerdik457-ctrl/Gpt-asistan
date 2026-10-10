#!/usr/bin/env python3
"""Bir klasörü zip'leyip Google Drive'a yükler.

Env:
  GOOGLE_SERVICE_ACCOUNT_JSON  Servis hesabı JSON içeriği (veya dosya yolu)
  DRIVE_FOLDER_ID              Hedef Drive klasör ID'si (servis hesabıyla paylaşılmış)
  BACKUP_SOURCE                Yedeklenecek klasör (varsayılan: .)
"""
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone

EXCLUDE_DIRS = {".git", ".gradle", "build", "node_modules", "__pycache__", ".idea"}
EXCLUDE_FILES = {".env"}


def make_zip(source, out_path):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(source):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                if f in EXCLUDE_FILES:
                    continue
                full = os.path.join(root, f)
                if os.path.abspath(full) == os.path.abspath(out_path):
                    continue
                z.write(full, os.path.relpath(full, source))


def load_credentials(raw):
    from google.oauth2 import service_account
    info = json.load(open(raw)) if os.path.isfile(raw) else json.loads(raw)
    return service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.file"])


def main():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    folder = os.environ.get("DRIVE_FOLDER_ID")
    source = os.environ.get("BACKUP_SOURCE", ".")
    if not raw or not folder:
        sys.exit("GOOGLE_SERVICE_ACCOUNT_JSON ve DRIVE_FOLDER_ID tanımlı olmalı.")
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    name = "gpt-asistan-backup-%s.zip" % datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, name)
        make_zip(source, path)
        service = build("drive", "v3", credentials=load_credentials(raw), cache_discovery=False)
        media = MediaFileUpload(path, mimetype="application/zip", resumable=True)
        res = service.files().create(
            body={"name": name, "parents": [folder]}, media_body=media,
            fields="id,name", supportsAllDrives=True).execute()
    print("Yüklendi: %s (id=%s)" % (res["name"], res["id"]))


if __name__ == "__main__":
    main()
