"""Exact gateway instrumentation acceptance, with all ADB and fixture processes mocked."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import run_android_gateway_acceptance as runner


def instrumentation_output(names=None):
    names = sorted(runner.EXPECTED_TESTS) if names is None else names
    blocks = []
    for name in names:
        for status in (1, 0):
            blocks.append(
                "INSTRUMENTATION_STATUS: class=" + runner.TEST_CLASS + "\n"
                "INSTRUMENTATION_STATUS: numtests=4\n"
                "INSTRUMENTATION_STATUS: test=" + name + "\n"
                "INSTRUMENTATION_STATUS_CODE: " + str(status) + "\n")
    return "".join(blocks) + "\nOK (4 tests)\nINSTRUMENTATION_CODE: -1\n"


class InstrumentationParserTests(unittest.TestCase):
    def test_requires_four_individually_named_passes(self):
        result = runner.parse_instrumentation(instrumentation_output())
        self.assertTrue(result["instrumentation_passed"])
        self.assertEqual(result["instrumentation_tests"], 4)
        self.assertEqual(set(result["passed_tests"]), runner.EXPECTED_TESTS)
        self.assertEqual(result["skipped_tests"], 0)

    def test_rejects_missing_duplicate_or_unexpected_tests(self):
        names = sorted(runner.EXPECTED_TESTS)
        for output in (
                instrumentation_output(names[:-1]),
                instrumentation_output(names[:-1] + [names[0]]),
                instrumentation_output(names[:-1] + ["anotherTest"]),
                instrumentation_output().replace(runner.TEST_CLASS, "other.Test"),
                "OK (4 tests)\nINSTRUMENTATION_CODE: -1\n"):
            with self.subTest(output=output):
                with self.assertRaises(runner.AcceptanceError):
                    runner.parse_instrumentation(output)

    def test_rejects_zero_skipped_ignored_failure_and_runner_errors(self):
        valid = instrumentation_output()
        outputs = (
            valid.replace("OK (4 tests)", "OK (0 tests)"),
            valid.replace("OK (4 tests)", "OK (5 tests)"),
            valid.replace("numtests=4", "numtests=0", 1),
            valid.replace("INSTRUMENTATION_STATUS_CODE: 0", "INSTRUMENTATION_STATUS_CODE: -3", 1),
            valid.replace("INSTRUMENTATION_STATUS_CODE: 0", "INSTRUMENTATION_STATUS_CODE: -4", 1),
            valid.replace("INSTRUMENTATION_STATUS_CODE: 0", "INSTRUMENTATION_STATUS_CODE: -2", 1),
            valid.replace("INSTRUMENTATION_CODE: -1", "INSTRUMENTATION_CODE: 0"),
            valid.replace("OK (4 tests)", "FAILURES!!!"),
            valid + "INSTRUMENTATION_FAILED: crash\n",
            valid + "AssumptionViolatedException: fixture missing\n",
            valid + "Ignored test\n",
            valid + "Skipped 1 test\n",
        )
        for output in outputs:
            with self.subTest(output=output):
                with self.assertRaises(runner.AcceptanceError):
                    runner.parse_instrumentation(output)


class AndroidGatewayRunnerTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.app, self.test = self.root / "app.apk", self.root / "test.apk"
        self.app.write_bytes(b"synthetic app fixture")
        self.test.write_bytes(b"synthetic instrumentation fixture")
        self.evidence = self.root / "evidence"
        self.arguments = {
            "kralFixtureBase": "https://localhost:48123", "kralFixtureCa": "Q0VSVElGSUNBVEU=",
            "kralFixtureOwnerPrivate": "T1dORVJQUklWQVRF", "kralFixtureDevicePrivate": "REVWSUNFUFJJVkFURQ==",
            "kralFixtureDeviceId": "a" * 64,
        }
        self.counters = {"mocked_responses_calls": 8, "external_provider_calls": 0,
                         "completed": 2, "typed_failures": 6}

    def adb(self, *arguments, **_kwargs):
        values = {
            ("get-state",): "device\n",
            ("shell", "getprop", "ro.kernel.qemu"): "1\n",
            ("shell", "getprop", "sys.boot_completed"): "1\n",
            ("shell", "getprop", "ro.build.version.sdk"): "30\n",
        }
        stdout = values.get(arguments, "")
        if arguments[:3] == ("shell", "am", "instrument"):
            stdout = instrumentation_output() + "private fixture=" + self.arguments["kralFixtureOwnerPrivate"]
        return subprocess.CompletedProcess(arguments, 0, stdout, "")

    def test_installs_runs_exact_class_redacts_and_cleans_up(self):
        process = Mock(pid=1122, returncode=0)
        process.poll.return_value = None
        with patch.object(runner, "_adb", side_effect=self.adb) as adb, \
             patch.object(runner.subprocess, "Popen", return_value=process) as launch, \
             patch.object(runner, "_wait_ready", return_value=(48123, self.arguments)), \
             patch.object(runner, "_fixture_evidence", return_value=self.counters):
            summary = runner.run_acceptance(self.app, self.test, self.evidence)
        self.assertTrue(summary["instrumentation_passed"])
        self.assertFalse(summary["physical_phone_tested"])
        self.assertFalse(summary["live_model_tested"])
        self.assertEqual(summary["api_level"], 30)
        self.assertEqual(summary["fixture_evidence"], self.counters)
        command = next(call.args for call in adb.call_args_list if call.args[:3] == ("shell", "am", "instrument"))
        self.assertIn(runner.TEST_CLASS, command)
        self.assertEqual(command[-1], runner.TEST_RUNNER)
        for name, value in self.arguments.items():
            self.assertIn(name, command)
            self.assertIn(value, command)
        adb.assert_any_call("install", "-r", "-t", str(self.app), timeout=90)
        adb.assert_any_call("install", "-r", "-t", str(self.test), timeout=90)
        adb.assert_any_call("reverse", "tcp:48123", "tcp:48123")
        adb.assert_any_call("reverse", "--remove", "tcp:48123")
        fixture_command = launch.call_args.args[0]
        self.assertEqual(fixture_command[:3], [sys.executable, "-m", "scripts.android_gateway_fixture"])
        private_ready = Path(fixture_command[-1])
        self.assertFalse(private_ready.parent.exists())
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=10)
        artifacts = "".join(path.read_text() for path in self.evidence.iterdir())
        for value in self.arguments.values():
            self.assertNotIn(value, artifacts)
        self.assertIn("[REDACTED_FIXTURE_ARGUMENT]", artifacts)
        self.assertEqual(json.loads((self.evidence / "fixture-evidence.json").read_text()), self.counters)

    def test_failed_instrumentation_still_removes_reverse_and_stops_fixture(self):
        def failed_adb(*arguments, **kwargs):
            if arguments[:3] == ("shell", "am", "instrument"):
                return subprocess.CompletedProcess(arguments, 0, "OK (0 tests)\nINSTRUMENTATION_CODE: -1\n", "")
            return self.adb(*arguments, **kwargs)
        process = Mock(pid=1122, returncode=0)
        process.poll.return_value = None
        with patch.object(runner, "_adb", side_effect=failed_adb) as adb, \
             patch.object(runner.subprocess, "Popen", return_value=process), \
             patch.object(runner, "_wait_ready", return_value=(48123, self.arguments)), \
             patch.object(runner, "_fixture_evidence", return_value=self.counters):
            summary = runner.run_acceptance(self.app, self.test, self.evidence)
        self.assertFalse(summary["instrumentation_passed"])
        self.assertEqual(summary["error"], "INSTRUMENTATION_EXACT_COUNT_REQUIRED")
        adb.assert_any_call("reverse", "--remove", "tcp:48123")
        process.terminate.assert_called_once()

    def test_physical_device_check_precedes_install_and_fixture_start(self):
        def physical_adb(*arguments, **kwargs):
            if arguments == ("shell", "getprop", "ro.kernel.qemu"):
                return subprocess.CompletedProcess(arguments, 0, "0\n", "")
            return self.adb(*arguments, **kwargs)
        with patch.object(runner, "_adb", side_effect=physical_adb) as adb, \
             patch.object(runner.subprocess, "Popen") as launch:
            summary = runner.run_acceptance(self.app, self.test, self.evidence)
        self.assertFalse(summary["instrumentation_passed"])
        self.assertEqual(summary["error"], "PHYSICAL_DEVICE_DENIED")
        launch.assert_not_called()
        self.assertFalse(any(call.args[0] == "install" for call in adb.call_args_list))

    def test_fixture_cleanup_escalates_only_after_bounded_wait(self):
        process = Mock(returncode=0)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("private command", 10), 0]
        runner._stop_fixture(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual([call.kwargs["timeout"] for call in process.wait.call_args_list], [10, 5])


if __name__ == "__main__":
    unittest.main()
