#!/usr/bin/env python3
"""Summarize actual Gradle XML results beside the exact-source APK artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def summarize(tests: Path, lint: Path) -> dict:
    files = sorted(tests.glob("TEST-*.xml"))
    if not files:
        raise ValueError("UNIT_TEST_RESULTS_MISSING")
    counts = dict(tests=0, failures=0, errors=0, skipped=0)
    skipped_tests = []
    for path in files:
        suite = ET.parse(path).getroot()
        if suite.tag != "testsuite":
            raise ValueError("UNIT_TEST_XML_INVALID")
        for key in counts:
            counts[key] += int(suite.get(key, "0"))
        for case in suite.findall("testcase"):
            skipped = case.find("skipped")
            if skipped is not None:
                skipped_tests.append({"classname": case.get("classname"), "name": case.get("name"),
                                      "reason": skipped.get("message") or skipped.text or "JUnit skipped; not counted as passed"})
    if counts["tests"] <= counts["skipped"] or counts["failures"] or counts["errors"]:
        raise ValueError("UNIT_TESTS_NOT_PASSED")
    if len(skipped_tests) != counts["skipped"] or any(
        not case["classname"] or not case["name"] for case in skipped_tests
    ):
        raise ValueError("SKIPPED_TEST_IDENTITIES_MISSING")
    issues = ET.parse(lint).getroot()
    if issues.tag != "issues":
        raise ValueError("LINT_XML_INVALID")
    severities: dict[str, int] = {}
    issue_counts: dict[str, int] = {}
    for issue in issues.findall("issue"):
        level = issue.get("severity", "Unknown")
        severities[level] = severities.get(level, 0) + 1
        issue_id = issue.get("id", "Unknown")
        issue_counts[issue_id] = issue_counts.get(issue_id, 0) + 1
    if severities.get("Error", 0) or severities.get("Fatal", 0):
        raise ValueError("LINT_ERRORS_PRESENT")
    return {"unit_tests": counts, "unit_tests_passed": counts["tests"] - counts["skipped"],
            "skipped_tests": skipped_tests,
            "lint": {"passed": True, "severities": severities, "issue_counts": issue_counts}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    metadata = json.loads((args.output / "apk-metadata.json").read_text())
    if not metadata["exact_source_head_verified"] or not metadata["source_tree_clean"]:
        raise ValueError("SOURCE_NOT_VERIFIED")
    evidence = summarize(Path("app/build/test-results/testDebugUnitTest"),
                         Path("app/build/reports/lint-results-debug.xml"))
    evidence.update(source_commit=metadata["source_commit"], apk_sha256=metadata["sha256"],
                    github_run_id=metadata["github_run_id"],
                    emulator_results="Separate API 30/36 job artifacts; not assumed at build time",
                    physical_phone_tested=False, live_model_tested=False)
    (args.output / "test-summary.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
