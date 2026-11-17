"""Run exactly the four gateway acceptance tests on a disposable Android emulator.

The existing HTTPS fixture uses synthetic identities and mocked OpenAI transport.
Fixture arguments and private ready files are never printed or retained as artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


TEST_CLASS = "com.example.gptasistan.OwnerGatewayIntegrationTest"
TEST_RUNNER = "com.example.gptasistan.genesis.test/androidx.test.runner.AndroidJUnitRunner"
EXPECTED_TESTS = frozenset({
    "signedAndroidTaskReachesGatewayAndReturnsResponsesEvidence",
    "providerAccessFailuresRemainTypedInTheTaskContract",
    "chatHttpErrorsUseTheSameTypedAndroidFailureParser",
    "signedLocalMemoryRequiresExactApprovalAndExecutesOnlyOnce",
})
FIXTURE_ARGUMENTS = frozenset({
    "kralFixtureBase", "kralFixtureCa", "kralFixtureOwnerPrivate",
    "kralFixtureDevicePrivate", "kralFixtureDeviceId",
})
ROOT = Path(__file__).resolve().parents[1]


class AcceptanceError(ValueError):
    pass


def parse_instrumentation(output):
    """Require four actual passes, rather than a runner summary that includes skips."""
    output = output.replace("\r", "")
    if any(marker in output for marker in ("FAILURES!!!", "INSTRUMENTATION_FAILED", "INSTRUMENTATION_ABORTED")):
        raise AcceptanceError("INSTRUMENTATION_FAILURE")
    if re.search(r"(?i)AssumptionViolated|\bskipped\b|\bignored\b", output):
        raise AcceptanceError("INSTRUMENTATION_SKIP_DENIED")
    summaries = re.findall(r"(?m)^\s*OK\s+\((\d+)\s+tests?\)\s*$", output)
    if summaries != ["4"]:
        raise AcceptanceError("INSTRUMENTATION_EXACT_COUNT_REQUIRED")
    result_codes = re.findall(r"(?m)^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$", output)
    if result_codes != ["-1"]:
        raise AcceptanceError("INSTRUMENTATION_RESULT_CODE_INVALID")
    fields, passed = {}, []
    for line in output.splitlines():
        field = re.fullmatch(r"INSTRUMENTATION_STATUS: ([A-Za-z]+)=(.*)", line)
        if field:
            fields[field[1]] = field[2]
            if field[1] == "numtests" and field[2] != "4":
                raise AcceptanceError("INSTRUMENTATION_EXACT_COUNT_REQUIRED")
        status = re.fullmatch(r"INSTRUMENTATION_STATUS_CODE:\s*(-?\d+)\s*", line)
        if status:
            code = int(status[1])
            if code not in (0, 1):
                raise AcceptanceError("INSTRUMENTATION_TEST_NOT_PASSED")
            if code == 0:
                if fields.get("class") != TEST_CLASS or fields.get("test") not in EXPECTED_TESTS:
                    raise AcceptanceError("INSTRUMENTATION_UNEXPECTED_TEST")
                passed.append(fields["test"])
            fields = {}
    if len(passed) != 4 or set(passed) != EXPECTED_TESTS:
        raise AcceptanceError("INSTRUMENTATION_TEST_EVIDENCE_MISSING")
    return {"instrumentation_tests": 4, "passed_tests": passed,
            "skipped_tests": 0, "instrumentation_passed": True}


def redact(output, arguments):
    for value in sorted(arguments.values(), key=len, reverse=True):
        output = output.replace(value, "[REDACTED_FIXTURE_ARGUMENT]")
    return output


def _adb(*arguments, timeout=20, require_success=True):
    try:
        result = subprocess.run(["adb", "-e", *arguments], capture_output=True,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise AcceptanceError("ADB_UNAVAILABLE_OR_TIMED_OUT") from None
    if require_success and result.returncode != 0:
        # CalledProcessError would expose command arguments containing fixture keys.
        raise AcceptanceError("ADB_COMMAND_FAILED")
    return result


def _wait_ready(process, path, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AcceptanceError("FIXTURE_EXITED_BEFORE_READY")
        try:
            info = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.05)
            continue
        if not isinstance(info, dict):
            raise AcceptanceError("FIXTURE_READY_INVALID")
        arguments, port = info.get("instrumentation_args"), info.get("port")
        if (type(port) is not int or not 1 <= port <= 65535 or info.get("pid") != process.pid or
                not isinstance(arguments, dict) or set(arguments) != FIXTURE_ARGUMENTS or
                any(not isinstance(value, str) or not value or len(value) > 16384 or
                    "\n" in value or "\r" in value for value in arguments.values()) or
                arguments["kralFixtureBase"] != "https://localhost:" + str(port) or
                not re.fullmatch(r"[a-f0-9]{64}", arguments["kralFixtureDeviceId"]) or
                any(not re.fullmatch(r"[A-Za-z0-9+/=]+", arguments[name]) for name in (
                    "kralFixtureCa", "kralFixtureOwnerPrivate", "kralFixtureDevicePrivate"))):
            raise AcceptanceError("FIXTURE_READY_INVALID")
        return port, arguments
    raise AcceptanceError("FIXTURE_READY_TIMEOUT")


def _stop_fixture(process):
    if process.poll() is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            raise AcceptanceError("FIXTURE_TERMINATION_FAILED") from None
    if process.returncode != 0:
        raise AcceptanceError("FIXTURE_SHUTDOWN_FAILED")


def _fixture_evidence(path):
    try:
        document = json.loads(path.read_text())
        names = ("mocked_responses_calls", "external_provider_calls", "completed", "typed_failures")
        if (not isinstance(document, dict) or
                any(type(document.get(name)) is not int or document[name] < 0 for name in names)):
            raise ValueError
        evidence = {name: document[name] for name in names}
        if evidence["external_provider_calls"] != 0:
            raise AcceptanceError("FIXTURE_EXTERNAL_CALL_DENIED")
        return evidence
    except AcceptanceError:
        raise
    except (OSError, ValueError, KeyError):
        raise AcceptanceError("FIXTURE_EVIDENCE_INVALID") from None


def run_acceptance(app_apk, test_apk, evidence_dir):
    app_apk, test_apk, evidence_dir = Path(app_apk).resolve(), Path(test_apk).resolve(), Path(evidence_dir).resolve()
    if not app_apk.is_file() or not test_apk.is_file():
        raise AcceptanceError("APK_INPUT_MISSING")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths = {name: evidence_dir / name for name in (
        "instrumentation-result.txt", "summary.json", "fixture-evidence.json")}
    if any(path.exists() for path in artifact_paths.values()):
        raise AcceptanceError("EVIDENCE_ALREADY_EXISTS")
    summary = {"instrumentation_tests": 0, "passed_tests": [], "instrumentation_passed": False,
               "expected_tests": sorted(EXPECTED_TESTS), "physical_phone_tested": False,
               "live_model_tested": False, "external_provider_calls": 0}
    output, fixture_counts, error = "", None, None
    with tempfile.TemporaryDirectory(prefix="kral-gateway-acceptance-") as private:
        private_root = Path(private).resolve()
        if private_root.is_relative_to(evidence_dir):
            raise AcceptanceError("PRIVATE_FIXTURE_PATH_OVERLAPS_EVIDENCE")
        ready = private_root / "ready.json"
        process, port, arguments, reversed_port = None, None, {}, False
        try:
            if _adb("get-state").stdout.strip() != "device":
                raise AcceptanceError("EMULATOR_NOT_READY")
            if _adb("shell", "getprop", "ro.kernel.qemu").stdout.strip() != "1":
                raise AcceptanceError("PHYSICAL_DEVICE_DENIED")
            if _adb("shell", "getprop", "sys.boot_completed").stdout.strip() != "1":
                raise AcceptanceError("EMULATOR_BOOT_INCOMPLETE")
            api = _adb("shell", "getprop", "ro.build.version.sdk").stdout.strip()
            if not api.isdigit():
                raise AcceptanceError("EMULATOR_API_INVALID")
            summary["api_level"] = int(api)
            process = subprocess.Popen(
                [sys.executable, "-m", "scripts.android_gateway_fixture", "--ready-file", str(ready)],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            port, arguments = _wait_ready(process, ready)
            _adb("install", "-r", "-t", str(app_apk), timeout=90)
            _adb("install", "-r", "-t", str(test_apk), timeout=90)
            _adb("reverse", "tcp:" + str(port), "tcp:" + str(port))
            reversed_port = True
            command = ["shell", "am", "instrument", "-w", "-r", "-e", "class", TEST_CLASS]
            for name, value in sorted(arguments.items()):
                command.extend(("-e", name, value))
            command.append(TEST_RUNNER)
            result = _adb(*command, timeout=240, require_success=False)
            output = redact(result.stdout + result.stderr, arguments)
            if result.returncode != 0:
                raise AcceptanceError("ADB_INSTRUMENTATION_FAILED")
            summary.update(parse_instrumentation(output))
        except AcceptanceError as failure:
            error = str(failure)
        except (OSError, ValueError, TypeError):
            error = "ANDROID_ACCEPTANCE_FAILED"
        finally:
            if reversed_port:
                try:
                    _adb("reverse", "--remove", "tcp:" + str(port))
                except AcceptanceError:
                    error = error or "ADB_REVERSE_CLEANUP_FAILED"
            if process is not None:
                try:
                    _stop_fixture(process)
                    fixture_counts = _fixture_evidence(ready.with_suffix(".evidence.json"))
                except AcceptanceError as failure:
                    error = error or str(failure)
        if fixture_counts is not None:
            summary["fixture_evidence"] = fixture_counts
        if error:
            summary["instrumentation_passed"] = False
            summary["error"] = error
        artifact_paths["instrumentation-result.txt"].write_text(output)
        artifact_paths["summary.json"].write_text(json.dumps(summary, indent=2) + "\n")
        if fixture_counts is not None:
            artifact_paths["fixture-evidence.json"].write_text(json.dumps(fixture_counts, indent=2) + "\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-apk", type=Path, required=True)
    parser.add_argument("--test-apk", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_acceptance(args.app_apk, args.test_apk, args.evidence_dir)
    except (AcceptanceError, OSError):
        result = {"instrumentation_passed": False, "error": "ANDROID_ACCEPTANCE_PREREQUISITE_FAILED",
                  "physical_phone_tested": False, "live_model_tested": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["instrumentation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
