#!/usr/bin/env python3
"""Verify individual Android results and require coverage of skipped JVM tests."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re


def verify(data: str, unit_summary: dict, source_sha: str, apk_sha256: str) -> dict:
    if unit_summary["source_commit"] != source_sha or unit_summary["apk_sha256"] != apk_sha256:
        raise ValueError("INSTRUMENTATION_BUILD_IDENTITY_MISMATCH")
    data = data.replace("\r", "")
    match = re.search(r"(?m)^\s*OK\s+\((\d+)\s+tests?\)\s*$", data)
    if match is None or not re.search(r"(?m)^INSTRUMENTATION_CODE:\s*-1\s*$", data):
        raise ValueError("INSTRUMENTATION_SUCCESS_SUMMARY_MISSING")
    count = int(match.group(1))
    if count < 16 or "FAILURES!!!" in data or "INSTRUMENTATION_FAILED" in data:
        raise ValueError("INSTRUMENTATION_FAILURE_OR_REGRESSION")
    current = {}
    started, passed = set(), set()
    for line in data.splitlines():
        status = re.fullmatch(r"INSTRUMENTATION_STATUS: (class|test)=(.+)", line)
        if status:
            current[status.group(1)] = status.group(2)
        code = re.fullmatch(r"INSTRUMENTATION_STATUS_CODE:\s*(-?\d+)\s*", line)
        if code:
            key = (current.get("class"), current.get("test"))
            if not all(key):
                raise ValueError("INSTRUMENTATION_TEST_ID_MISSING")
            if code.group(1) == "1":
                if key in started:
                    raise ValueError("INSTRUMENTATION_DUPLICATE_TEST")
                started.add(key)
            elif code.group(1) == "0":
                if key not in started or key in passed:
                    raise ValueError("INSTRUMENTATION_TEST_SEQUENCE_INVALID")
                passed.add(key)
            else:
                raise ValueError("INSTRUMENTATION_TEST_NOT_PASSED")
            current = {}
    if len(passed) != count or passed != started:
        raise ValueError("INSTRUMENTATION_TEST_COUNT_MISMATCH")
    skipped = unit_summary["skipped_tests"]
    if len(skipped) != unit_summary["unit_tests"]["skipped"]:
        raise ValueError("JVM_SKIPPED_TEST_IDENTITIES_MISSING")
    required = {(case["classname"], case["name"]) for case in skipped}
    if len(required) != len(skipped) or not required <= passed:
        raise ValueError("JVM_SKIPPED_TEST_NOT_COVERED_ON_ANDROID")
    return {"instrumentation_tests": count, "instrumentation_passed": True,
            "passed_tests": [{"classname": c, "name": n} for c, n in sorted(passed)],
            "jvm_skips_covered_on_android": [{"classname": c, "name": n} for c, n in sorted(required)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("build_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    metadata = json.loads((args.build_directory / "apk-metadata.json").read_text())
    summary = json.loads((args.build_directory / "test-summary.json").read_text())
    result = verify(args.log.read_text(errors="replace"), summary,
                    os.environ["KRAL_EXPECTED_SOURCE_SHA"], metadata["sha256"])
    result.update(source_commit=os.environ["KRAL_EXPECTED_SOURCE_SHA"], apk_sha256=metadata["sha256"],
                  github_run_id=os.environ["GITHUB_RUN_ID"], api_level=int(os.environ["KRAL_EMULATOR_API"]),
                  physical_phone_tested=False, live_model_tested=False, owner_authentication_attempted=False)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
