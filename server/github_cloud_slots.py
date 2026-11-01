"""Bounded, evidence-backed GitHub-hosted process workers, NOT AI sessions.

Orchestrates 50 GitHub Actions matrix process slots. Each job executes
allowlisted unit tests and a public read-only GitHub GET through the existing
worker_proof module. This does not dispatch Copilot or run model inference.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from server import worker_proof

SLOTS = 50
MAX_PARALLEL = 4
ROLES = (
    "github-master-ai", "chief-engineer", "android-engineer",
    "ai-ml-engineer", "mcp-engineer", "ci-cd-engineer",
    "test-engineer", "security-auditor",
)
HEX_SHA = re.compile(r"[a-f0-9]{40}\Z")


class InvalidEvidence(ValueError):
    pass


def role_for_slot(slot: int) -> str:
    if type(slot) is not int or not 1 <= slot <= SLOTS:
        raise InvalidEvidence("SLOT_OUT_OF_RANGE")
    return ROLES[(slot - 1) % len(ROLES)]


def run_slot(slot: int, *, execute_role=None) -> dict:
    role = role_for_slot(slot)
    runner = worker_proof.execute_role if execute_role is None else execute_role
    proof = runner(role)
    if not isinstance(proof, dict) or proof.get("role") != role:
        raise InvalidEvidence("ROLE_PROOF_MISMATCH")
    if proof.get("mode") != "REAL_PROCESS_PROBE_PASS_NO_MODEL":
        raise InvalidEvidence("PROBE_NOT_PASSED")
    if proof.get("real_ai_model_calls") != 0 or proof.get("code_changes") != 0:
        raise InvalidEvidence("UNEXPECTED_MODEL_OR_WRITE")
    return {**proof, "cloud_slot_schema": 1, "slot": slot,
            "worker_id": f"worker-{slot:02d}",
            "execution_type": "GITHUB_ACTIONS_READONLY_PROCESS_NOT_AI"}


def verify_all(directory: Path, *, expected_sha: str, expected_run_id: str) -> dict:
    if not HEX_SHA.fullmatch(expected_sha):
        raise InvalidEvidence("EXPECTED_SHA_INVALID")
    if not expected_run_id.isdecimal() or int(expected_run_id) < 1:
        raise InvalidEvidence("RUN_ID_INVALID")
    if not directory.is_dir() or directory.is_symlink():
        raise InvalidEvidence("EVIDENCE_DIRECTORY_MISSING")
    expected_names = {f"kral-cloud-slot-{n}" for n in range(1, SLOTS + 1)}
    actual = {path.name for path in directory.iterdir()}
    if actual != expected_names:
        raise InvalidEvidence("MISSING_OR_EXTRA_SLOT_ARTIFACT")
    for slot in range(1, SLOTS + 1):
        folder = directory / f"kral-cloud-slot-{slot}"
        file = folder / "kral-cloud-slot.json"
        if folder.is_symlink() or not folder.is_dir() or file.is_symlink() or not file.is_file():
            raise InvalidEvidence("ARTIFACT_PATH_DENIED")
        if file.stat().st_size > 8192:
            raise InvalidEvidence("OVERSIZE_SLOT_ARTIFACT")
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise InvalidEvidence("CORRUPT_SLOT_ARTIFACT") from exc
        if not isinstance(data, dict):
            raise InvalidEvidence("BAD_SLOT_ARTIFACT")
        checks = {
            "cloud_slot_schema": 1, "schema": 1,
            "slot": slot, "worker_id": f"worker-{slot:02d}",
            "role": role_for_slot(slot),
            "execution_type": "GITHUB_ACTIONS_READONLY_PROCESS_NOT_AI",
            "mode": "REAL_PROCESS_PROBE_PASS_NO_MODEL",
            "test_result": "PASS", "github_read": "LIVE_PUBLIC_GITHUB_READ",
            "github_actions_run_id": expected_run_id,
            "source_sha": expected_sha,
            "logical_worker_slot_capacity": SLOTS,
            "real_ai_model_calls": 0, "code_changes": 0,
            "owner_acceptance": "NOT_GRANTED",
        }
        if any(type(data.get(key)) is not type(value) or data.get(key) != value
               for key, value in checks.items()):
            raise InvalidEvidence(f"SLOT_{slot:02d}_EVIDENCE_MISMATCH")
        for key in ("profile_sha256", "test_output_sha256"):
            digest = data.get(key)
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise InvalidEvidence(f"SLOT_{slot:02d}_HASH_INVALID")
    return {
        "schema": 1, "mode": "FIFTY_GITHUB_ACTIONS_PROCESS_SLOTS_VERIFIED_NO_AI",
        "source_sha": expected_sha, "github_actions_run_id": expected_run_id,
        "total_expected_slots": SLOTS, "verified_process_slots": SLOTS,
        "max_parallel_jobs": MAX_PARALLEL, "real_ai_model_calls": 0,
        "copilot_sessions_started": 0, "github_write_tasks_completed": 0,
        "owner_acceptance": "NOT_GRANTED",
    }


def write_exclusive(path: Path, payload: dict) -> None:
    if not path.parent.is_dir() or path.parent.is_symlink() or path.is_symlink():
        raise InvalidEvidence("EVIDENCE_DESTINATION_DENIED")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(payload, out, ensure_ascii=False, sort_keys=True, indent=2)
        out.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="50 GitHub-hosted read-only process probes")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slot", type=int)
    group.add_argument("--verify-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.slot is not None:
            result = run_slot(args.slot)
        else:
            result = verify_all(args.verify_dir,
                                expected_sha=os.environ.get("GITHUB_SHA", ""),
                                expected_run_id=os.environ.get("GITHUB_RUN_ID", ""))
        write_exclusive(args.out, result)
        print(json.dumps({"mode": result["mode"],
                          "slot": result.get("slot", "ROLLUP"),
                          "evidence": str(args.out)}, sort_keys=True))
        return 0
    except (InvalidEvidence, OSError, ValueError, TypeError, KeyError) as exc:
        print("KRAL_CLOUD_SLOTS_BLOCKED:" + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
