#!/usr/bin/env python3
"""Upload a file (or a zip of a directory) to Google Drive.

Credentials come only from the environment:
  GDRIVE_SERVICE_ACCOUNT_JSON  service-account key JSON (content, not path)
  GDRIVE_OAUTH_TOKEN_JSON      authorized-user token JSON (content), alternative
  GDRIVE_FOLDER_ID             target Drive folder ID (share it with the service account)
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def build_credentials(env=os.environ):
    sa = env.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    tok = env.get("GDRIVE_OAUTH_TOKEN_JSON")
    if sa:
        from google.oauth2 import service_account
        return service_account.Credentials.from_service_account_info(json.loads(sa), scopes=SCOPES)
    if tok:
        from google.oauth2.credentials import Credentials
        return Credentials.from_authorized_user_info(json.loads(tok), SCOPES)
    raise SystemExit("Set GDRIVE_SERVICE_ACCOUNT_JSON or GDRIVE_OAUTH_TOKEN_JSON")


def prepare(path):
    if os.path.isdir(path):
        base = os.path.join(tempfile.mkdtemp(), os.path.basename(os.path.abspath(path)))
        return shutil.make_archive(base, "zip", path)
    return path


def upload(path, folder_id):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    service = build("drive", "v3", credentials=build_credentials(), cache_discovery=False)
    media = MediaFileUpload(path, resumable=True)
    meta = {"name": os.path.basename(path), "parents": [folder_id]}
    created = service.files().create(body=meta, media_body=media, fields="id,name").execute()
    return created["id"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", help="file or directory to upload")
    ap.add_argument("--folder-id", default=os.environ.get("GDRIVE_FOLDER_ID"))
    args = ap.parse_args(argv)
    if not args.folder_id:
        sys.exit("GDRIVE_FOLDER_ID (or --folder-id) is required")
    if not os.path.exists(args.path):
        sys.exit("path not found: " + args.path)
    target = prepare(args.path)
    try:
        file_id = upload(target, args.folder_id)
    finally:
        if target != args.path:
            shutil.rmtree(os.path.dirname(target), ignore_errors=True)
    print("uploaded, Drive file id:", file_id)


if __name__ == "__main__":
    main()
