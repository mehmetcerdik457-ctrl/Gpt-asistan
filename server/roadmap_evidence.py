"""Offline roadmap evidence-contract verifier. Never upgrades old CI to PASS.

The 11 manifest filenames are contractual; existence is not acceptance.
The result is deliberately BLOCKED until exact-source, real deployment,
device identity, owner signing and Drive re-download checks all exist.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

REQUIRED_FILES = (
    "KRAL_SOURCE_MANIFEST.json",
    "KRAL_CAPABILITY_REGISTRY.json",
    "KRAL_DEPENDENCY_GRAPH.json",
    "KRAL_CONNECTION_STATUS.json",
    "KRAL_INTEGRATION_MANIFEST.json",
    "KRAL_TASK_LEDGER.json",
    "KRAL_TEST_RESULTS.json",
    "KRAL_SECURITY_EVENTS.json",
    "KRAL_BACKUP_RESTORE_STATUS.json",
    "KRAL_RELEASE_MANIFEST.json",
    "KRAL_BLOCKERS.json",
)
ACCEPTANCE_IDS = tuple(f"T{i:02d}" for i in range(1, 27))
ALLOWED_STATES = frozenset(("PASS", "PARTIAL", "BLOCKED", "NOT_TESTED", "REJECTED"))
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


class EvidenceInvalid(ValueError):
    pass


def audit(root: Path, *, target_commit: str) -> dict:
    if not SHA_PATTERN.fullmatch(target_commit):
        raise EvidenceInvalid("TARGET_COMMIT_NOT_FULL_SHA")
    path = root / "evidence" / "genesis-v128"
    manifests = {}
    for name in REQUIRED_FILES:
        file = path / name
        try:
            content = file.read_bytes()
        except OSError:
            raise EvidenceInvalid("REQUIRED_MANIFEST_MISSING:" + name) from None
        if len(content) > 2 * 1024 * 1024:
            raise EvidenceInvalid("MANIFEST_TOO_LARGE:" + name)
        try:
            obj = json.loads(content)
        except (TypeError, ValueError):
            raise EvidenceInvalid("MANIFEST_INVALID_JSON:" + name) from None
        if not isinstance(obj, dict) or obj.get("schema_version") != 1:
            raise EvidenceInvalid("MANIFEST_SCHEMA_INVALID:" + name)
        manifests[name] = obj

    tests = manifests["KRAL_TEST_RESULTS.json"].get("acceptance_tests")
    if not isinstance(tests, list) or len(tests) != len(ACCEPTANCE_IDS):
        raise EvidenceInvalid("T01_T26_COUNT_INVALID")
    ids = [test.get("id") if isinstance(test, dict) else None for test in tests]
    if tuple(ids) != ACCEPTANCE_IDS:
        raise EvidenceInvalid("T01_T26_ORDER_OR_DUPLICATE")
    for test in tests:
        if test.get("status") not in ALLOWED_STATES:
            raise EvidenceInvalid("T01_T26_STATUS_INVALID")
    recorded = manifests["KRAL_TEST_RESULTS.json"].get("source_commit")
    exact = recorded == target_commit
    counts = dict(Counter(test["status"] for test in tests))
    release = manifests["KRAL_RELEASE_MANIFEST.json"]
    independent_release_gate = all(
        release.get(field) is True for field in (
            "apk_file_independently_verified", "installed_package_verified",
            "installed_certificate_verified", "upgrade_data_preservation_verified",
            "physical_device_verified", "drive_upload_verified",
            "drive_redownload_hash_verified")
    )
    # No release can pass from a stale result or debug/unsigned APK.
    can_accept = (
        exact and independent_release_gate and
        release.get("candidate_source_commit") == target_commit and
        release.get("owner_signing_verified") is True and
        counts.get("PASS", 0) == 26
    )
    return {
        "target_commit": target_commit,
        "required_manifests_present": len(manifests),
        "stored_acceptance_commit": recorded,
        "acceptance_commit_matches_target": exact,
        "stored_test_states": counts,
        "stored_tests_count": len(tests),
        "product_final_acceptance": "PASS" if can_accept else "BLOCKED",
        "legacy_manifest_age_is_not_live_proof": True,
        "scope": "Repository evidence contract only; does not call Android, Drive, OpenAI or device",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--target-commit", required=True)
    args = parser.parse_args()
    try:
        report = audit(args.root, target_commit=args.target_commit)
    except EvidenceInvalid as exc:
        print(json.dumps({"status": "INVALID_EVIDENCE", "error_code": str(exc)}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    # A valid, honestly BLOCKED assessment is not a test runner error.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
