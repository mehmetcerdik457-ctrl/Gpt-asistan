#!/usr/bin/env python3
"""KRAL: locally prepare a privacy/data-access case packet; never submit it.

No OpenAI API, network, SMTP, auth, webhook, or account changes are attempted.
Account-specific data must be supplied at runtime, not committed into source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

OFFICIAL_PRIVACY = "https://privacy.openai.com/"
OFFICIAL_HELP = "https://help.openai.com/"
OFFICIAL_APPEAL = "https://openai.com/form/appeal/"
CASE_PATTERN = re.compile(r"[0-9]{5,16}\Z")


def case_number(value: str) -> str:
    if not CASE_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("case number must be 5–16 digits")
    return value


def build_packet(
    *, case_id: str, linked_case: str | None, account_email: str | None,
    user_id: str | None, request_id: str | None, extra_context: str | None,
) -> dict:
    if not case_id.isdigit():
        raise ValueError("invalid case number")
    facts = [
        "Please confirm the present status of the existing data-access request.",
        "Please explain a secure alternative identity-verification and data-delivery process if account login is unavailable.",
        "Please preserve eligible conversations, Projects, files and attachments pending resolution, and describe any applicable limits.",
        "This is not a deletion request or an attempt to create a duplicate account-reinstatement appeal.",
    ]
    message = (
        "Hello OpenAI Privacy Team,\n\n"
        f"This is a follow-up concerning existing privacy/data-access case #{case_id}.\n"
        + (f"Please cross-reference related case #{linked_case}.\n" if linked_case else "")
        + (f"Account email: {account_email}\n" if account_email else "")
        + (f"User ID: {user_id}\n" if user_id else "")
        + (f"Diagnostic request ID: {request_id}\n" if request_id else "")
        + "\n" + "\n".join(f"- {fact}" for fact in facts)
        + (f"\n\nAdditional verified context supplied by account owner:\n{extra_context}" if extra_context else "")
        + "\n\nRegards\nAccount owner\n"
    )
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PREPARED_NOT_SENT",
        "purpose": "existing_privacy_data_access_case_followup",
        "case_id": case_id,
        "related_case_id": linked_case,
        "subject": f"Data access follow-up — existing case #{case_id}",
        "message": message,
        "official_links": {"privacy": OFFICIAL_PRIVACY, "help": OFFICIAL_HELP, "appeal": OFFICIAL_APPEAL},
        "disclaimer": "This local packet does not submit an appeal, compel review, or change account status.",
    }


def secure_write(packet: dict, directory: Path) -> tuple[Path, str]:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise ValueError("output directory cannot be a symlink")
    os.chmod(directory, 0o700)
    data = (json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    name = "case_" + packet["case_id"] + "_privacy_packet.json"
    path = directory / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path, sha


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", required=True, type=case_number, help="Existing privacy/data-access case number")
    p.add_argument("--linked-case", type=case_number)
    p.add_argument("--request-id", help="Diagnostic ID copied from an error; no secrets")
    p.add_argument("--context", help="Verified additional context; don't supply credentials")
    p.add_argument("--directory", type=Path, default=Path.home() / ".local/share/kral/openai_cases")
    args = p.parse_args(argv)
    packet = build_packet(
        case_id=args.case,
        linked_case=args.linked_case,
        account_email=os.environ.get("KRAL_OPENAI_ACCOUNT_EMAIL"),
        user_id=os.environ.get("KRAL_OPENAI_ACCOUNT_USER_ID"),
        request_id=args.request_id,
        extra_context=args.context,
    )
    try:
        output, sha = secure_write(packet, args.directory)
    except FileExistsError:
        p.error("packet already exists; refusing to overwrite evidence")
    print(f"PREPARED_NOT_SENT: {output}")
    print(f"SHA256: {sha}")
    print("Manual official channel: " + OFFICIAL_PRIVACY)
    print("No email, appeal, or API request was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
