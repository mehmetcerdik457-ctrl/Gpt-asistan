"""Read-only GitHub Actions provider configuration gate.

Only boolean presence flags are accepted. No credential values, network calls,
model inference, or repository writes are performed by this module.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

PROVIDERS = {
    "openai": ("OPENAI_KEY_PRESENT", "OPENAI_MODELS_PRESENT"),
    "cloudflare_workers_ai": ("CF_TOKEN_PRESENT", "CF_ACCOUNT_PRESENT", "CF_MODEL_PRESENT"),
    "owner_gateway": ("OWNER_TOKEN_PRESENT", "OWNER_URL_PRESENT", "OWNER_HOST_PRESENT", "OWNER_MODEL_PRESENT"),
}


def evaluate(flags: dict[str, str]) -> dict:
    names = {name for fields in PROVIDERS.values() for name in fields}
    if set(flags) != names:
        raise ValueError("UNEXPECTED_FLAGS")
    if any(value not in ("true", "false") for value in flags.values()):
        raise ValueError("INVALID_FLAG")
    providers = {}
    for provider, required in PROVIDERS.items():
        missing = sorted(name for name in required if flags[name] != "true")
        providers[provider] = {
            "state": "CONFIGURED_NAME_FLAGS_ONLY" if not missing else "NOT_CONFIGURED",
            "missing_flag_names": missing,
        }
    ready = all(item["state"] == "CONFIGURED_NAME_FLAGS_ONLY" for item in providers.values())
    return {
        "schema": 1,
        "mode": "ALL_FLAGS_PRESENT_UNVERIFIED" if ready else "BLOCKED_MISSING_PROVIDER_CONFIG",
        "providers": providers,
        "credential_values_examined": 0,
        "provider_http_calls": 0,
        "real_model_inferences": 0,
        "copilot_sessions_started": 0,
        "owner_identity_attested": False,
        "credential_validity_attested": False,
        "account_billing_attested": False,
        "repository_writes": 0,
        "merge_authorized": False,
    }


def write_new(path: Path, payload: dict) -> None:
    if path.is_symlink() or not path.parent.is_dir():
        raise ValueError("INVALID_EVIDENCE_PATH")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only provider presence gate")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        names = {name for group in PROVIDERS.values() for name in group}
        result = evaluate({name: os.environ.get(name, "false") for name in names})
        write_new(args.out, result)
        print(json.dumps({"mode": result["mode"], "report": str(args.out)}))
        return 0 if result["mode"] == "ALL_FLAGS_PRESENT_UNVERIFIED" else 2
    except (OSError, ValueError, TypeError):
        print("PROVIDER_READINESS_BLOCKED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
