"""Read-only acceptance evidence for KRAL's existing local model bridge.

An HTTP 200 or model response is evidence of an endpoint, NOT proof of a
particular model's weights, a physical Android device, or completed coding work.
This module never starts services, edits repositories, or uses provider secrets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

MAX_CONFIG_BYTES = 16384


def read_provider(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError("PROVIDER_FILE_DENIED")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("PROVIDER_FORMAT_DENIED")
    return obj


def assess(provider: dict, *, infer: bool = False, backend=None) -> dict:
    if backend is None:
        from server import local_open_workers as backend
    # Existing backend enforces loopback HTTP, schema, model allowlist,
    # no redirects, no proxies, timeouts and bounded response lengths.
    backend.validate_backend(provider)
    installed = backend.probe(provider)
    report = {
        "schema": 1,
        "scope": "KRAL_LOCAL_PROVIDER_READ_ONLY_ACCEPTANCE",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_hint": ("TERMUX_PREFIX_PRESENT" if
                         os.environ.get("PREFIX", "").startswith("/data/data/com.termux/files/usr")
                         else "RUNTIME_NOT_ATTESTED"),
        "endpoint": provider["endpoint"],
        "model": provider["model"],
        "supervisor_model": provider["supervisor_model"],
        "installed_model_count": len(installed),
        "model_catalog_result": "PASS_MODEL_IDS_PRESENT",
        "inference_result": "NOT_REQUESTED",
        "owner_acceptance": "NOT_GRANTED",
        "model_binary_identity_attested": False,
        "repository_tasks_completed": 0,
        "github_writes": 0,
        "remote_service_calls": 0,
        "mode": "LOCAL_CATALOG_PASS_NO_INFERENCE",
    }
    if infer:
        response = backend.infer(
            provider, provider["model"], "test-engineer", "worker-01",
            "Read-only local acceptance probe",
            "Reply briefly in Turkish. No commands, secrets, or file changes.",
            "mehmetcerdik457-ctrl/Gpt-asistan",
        )
        # Do not copy model output into logs: only bounded digest and byte count.
        data = response.encode("utf-8")
        report.update(
            mode="LOCAL_INFERENCE_RESPONSE_PASS_NOT_TASK_COMPLETION",
            inference_result="HTTP_MODEL_RESPONSE_RECEIVED_NOT_WEIGHT_ATTESTATION",
            response_sha256=hashlib.sha256(data).hexdigest(),
            response_bytes=len(data),
        )
    return report


def write_new_private(path: Path, content: str) -> None:
    if not path.parent.is_dir() or path.is_symlink():
        raise ValueError("EVIDENCE_PATH_DENIED")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(content)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the existing localhost model without modifying the system")
    parser.add_argument("--provider", type=Path,
                        default=Path("missions/local_provider.example.json"))
    parser.add_argument("--infer", action="store_true", help="Also request one safe real localhost inference")
    parser.add_argument("--out", type=Path, help="Create a NEW mode-0600 evidence JSON file")
    args = parser.parse_args(argv)
    try:
        report = assess(read_provider(args.provider), infer=args.infer)
        content = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.out:
            write_new_private(args.out, content)
        print(content, end="")
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        # Do not log the exception message: provider errors may include URLs.
        print(json.dumps({"mode": "BLOCKED_LOCAL_PROVIDER", "error_type": type(exc).__name__,
                          "owner_acceptance": "NOT_GRANTED"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
