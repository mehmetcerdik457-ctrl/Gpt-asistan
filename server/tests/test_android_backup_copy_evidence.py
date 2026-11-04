"""Synthetic parser fixtures only; these tests never claim actual Android results."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from server.tests.test_android_delivery_evidence import module


class BackupCopyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.verifier = module("android_backup_copy_evidence")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evidence = self.root / "evidence"
        self.apks = self.root / "apks"
        self.evidence.mkdir()
        self.apks.mkdir()
        self.env = {"KRAL_EXPECTED_SOURCE_SHA": "a" * 40, "KRAL_EMULATOR_API": "30",
                    "GITHUB_RUN_ID": "987654321"}
        self.cert = "b" * 64
        (self.apks / "app-debug.apk").write_bytes(b"synthetic APK fixture, not an Android package")
        (self.apks / "app-debug-androidTest.apk").write_bytes(b"synthetic instrumentation APK fixture")
        self.apk_hash = hashlib.sha256((self.apks / "app-debug.apk").read_bytes()).hexdigest()
        self.test_hash = hashlib.sha256((self.apks / "app-debug-androidTest.apk").read_bytes()).hexdigest()
        self.metadata = {
            "source_commit": self.env["KRAL_EXPECTED_SOURCE_SHA"],
            "expected_source_commit": self.env["KRAL_EXPECTED_SOURCE_SHA"],
            "github_run_id": self.env["GITHUB_RUN_ID"], "package": self.verifier.PACKAGE,
            "apk": "app-debug.apk", "sha256": self.apk_hash,
            "size_bytes": (self.apks / "app-debug.apk").stat().st_size,
            "exact_source_head_verified": True, "source_tree_clean": True,
            "signature_verified": True, "debuggable": True, "standalone_apk": True,
            "signer_certificate_sha256": [self.cert],
        }
        self.write_metadata()
        (self.apks / "APK-SHA256SUMS").write_text(self.apk_hash + "  app-debug.apk\n")
        (self.apks / "TEST-APK-SHA256SUMS").write_text(self.test_hash + "  app-debug-androidTest.apk\n")
        self.put("app-badging.txt", "package: name='" + self.verifier.PACKAGE +
                 "' versionCode='8' versionName='test'\napplication-debuggable\n")
        self.put("test-badging.txt", "package: name='" + self.verifier.TEST_PACKAGE +
                 "' versionCode='8' versionName='test'\n")
        signature = ("Verifies\nVerified using v2 scheme (APK Signature Scheme v2): true\n"
                     "Number of signers: 1\nSigner #1 certificate SHA-256 digest: " + self.cert + "\n")
        self.put("app-signature.txt", signature)
        self.put("test-signature.txt", signature)
        for name, value in {"device-serial.txt": "emulator-5554\n", "qemu.txt": "1\n",
                            "api-level.txt": "30\n", "abi.txt": "x86_64\n"}.items():
            self.put(name, value)
        for name in ("app-before.txt", "test-before.txt", "app-between.txt", "test-between.txt"):
            self.put(name, "")
        for name in ("source-install-app", "source-install-test", "source-uninstall-app",
                     "source-uninstall-test", "target-install-app", "target-install-test"):
            self.put(name + ".txt", "Success\n")
        # An opaque synthetic ciphertext-shaped fixture; no cryptographic result is claimed here.
        archive = b"KRALBAK1" + struct.pack(">III", 1, 3, 310_000) + bytes(16 + 12) + struct.pack(">I", 32) + bytes(32)
        (self.evidence / "kral-installation-backup.bin").write_bytes(archive)
        self.archive_hash = hashlib.sha256(archive).hexdigest()
        for phase in ("export", "restore"):
            self.put(phase + "-result.txt", self.phase_log(phase))

    def put(self, name, text):
        (self.evidence / name).write_text(text)

    def write_metadata(self):
        (self.apks / "apk-metadata.json").write_text(json.dumps(self.metadata))

    def phase_log(self, phase):
        identity = ("INSTRUMENTATION_STATUS: class=" + self.verifier.TEST_CLASS + "\n"
                    "INSTRUMENTATION_STATUS: test=" + self.verifier.TEST_METHOD + "\n"
                    "INSTRUMENTATION_STATUS: numtests=1\nINSTRUMENTATION_STATUS: current=1\n")
        flags = self.verifier.COMMON_FLAGS | self.verifier.PHASE_FLAGS[phase]
        custom = {flag: "true" for flag in flags}
        custom.update(kral_backup_phase=phase, kral_backup_archive_sha256=self.archive_hash)
        results = "".join("INSTRUMENTATION_RESULT: " + key + "=" + value + "\n"
                          for key, value in sorted(custom.items()))
        return (identity + "INSTRUMENTATION_STATUS_CODE: 1\n" + identity +
                "INSTRUMENTATION_STATUS_CODE: 0\n" + results +
                "INSTRUMENTATION_RESULT: stream=\nTime: 0.1\n\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n")

    def verify(self):
        return self.verifier.verify(self.evidence, self.apks, self.env)

    def test_valid_fixture_reports_only_same_emulator_reinstallation(self):
        result = self.verify()
        self.assertEqual(result["validation_phase"], "complete")
        self.assertEqual(result["backup_archive_sha256"], self.archive_hash)
        self.assertEqual(result["apk_sha256"], self.apk_hash)
        self.assertEqual(result["test_apk_sha256"], self.test_hash)
        self.assertTrue(result["same_archive_verified_in_both_phases"])
        self.assertTrue(result["restore_verified"])
        self.assertTrue(result["reopen_verified"])
        self.assertFalse(result["physical_phone_tested"])
        self.assertFalse(result["second_device_identity_verified"])
        self.assertEqual([p["phase"] for p in result["phase_results"]], ["export", "restore"])

    def test_actual_apk_and_test_bytes_must_match_all_hash_records(self):
        for filename in ("app-debug.apk", "app-debug-androidTest.apk"):
            path = self.apks / filename
            original = path.read_bytes()
            with self.subTest(filename=filename):
                path.write_bytes(original + b"changed")
                with self.assertRaisesRegex(ValueError, "APK_HASH_MISMATCH"):
                    self.verify()
                path.write_bytes(original)

    def test_actual_package_and_signature_cannot_be_replaced_by_metadata_claim(self):
        for name, wrong, error in (
            ("app-badging.txt", "package: name='other.application'\napplication-debuggable\n", "ACTUAL_PACKAGE_MISMATCH"),
            ("test-badging.txt", "package: name='other.application.test'\n", "ACTUAL_PACKAGE_MISMATCH"),
            ("app-badging.txt", "package: name='" + self.verifier.PACKAGE + "'\n", "NOT_DEBUGGABLE"),
            ("test-signature.txt", (self.evidence / "test-signature.txt").read_text().replace(self.cert, "e" * 64),
             "APK_SIGNATURE_INVALID"),
        ):
            path = self.evidence / name
            original = path.read_text()
            with self.subTest(name=name, error=error):
                path.write_text(wrong)
                with self.assertRaisesRegex(ValueError, error):
                    self.verify()
                path.write_text(original)

    def test_preexisting_package_at_either_boundary_blocks_acceptance(self):
        for filename in ("app-before.txt", "test-before.txt", "app-between.txt", "test-between.txt"):
            with self.subTest(filename=filename):
                self.put(filename, "package:/data/app/existing/base.apk\n")
                with self.assertRaisesRegex(ValueError, "PREEXISTING_PACKAGE"):
                    self.verify()
                self.put(filename, "")

    def test_installation_requires_one_success_marker_without_failure(self):
        for output in ("Not Success\n", "Success\nFailure [INSTALL_FAILED]\n", "Success\nSuccess\n"):
            with self.subTest(output=output):
                self.put("source-uninstall-app.txt", output)
                with self.assertRaisesRegex(ValueError, "INSTALL_OR_UNINSTALL_FAILED"):
                    self.verify()

    def test_false_or_duplicate_native_result_and_wrong_archive_hash_are_rejected(self):
        original = self.phase_log("restore")
        variants = [
            original.replace("kral_backup_reopen_verified=true", "kral_backup_reopen_verified=false"),
            original.replace("kral_backup_archive_sha256=" + self.archive_hash, "kral_backup_archive_sha256=" + "f" * 64),
            original.replace("INSTRUMENTATION_CODE: -1", "INSTRUMENTATION_RESULT: kral_backup_restore_verified=true\nINSTRUMENTATION_CODE: -1"),
        ]
        for data in variants:
            with self.subTest(data=data):
                self.put("restore-result.txt", data)
                with self.assertRaisesRegex(ValueError, "NATIVE_RESULT_INVALID|DUPLICATE_RESULT_KEY"):
                    self.verify()

    def test_duplicate_missing_skipped_or_wrong_native_test_cannot_pass(self):
        original = self.phase_log("restore")
        variants = [
            original + original,
            original.replace("INSTRUMENTATION_STATUS_CODE: 0\n", ""),
            original.replace("INSTRUMENTATION_STATUS_CODE: 0", "INSTRUMENTATION_STATUS_CODE: -3"),
            original.replace(self.verifier.TEST_METHOD, "aDifferentTest"),
            original.replace("OK (1 test)", "OK (2 tests)"),
            original + "INSTRUMENTATION_CODE: -1\n",
        ]
        for data in variants:
            with self.subTest(data=data):
                self.put("restore-result.txt", data)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_preflight_and_export_gates_do_not_require_later_phase_files(self):
        for path in self.evidence.iterdir():
            if path.name not in {"app-badging.txt", "test-badging.txt", "app-signature.txt", "test-signature.txt"}:
                path.unlink()
        self.assertEqual(self.verifier.preflight(self.evidence, self.apks, self.env)["validation_phase"], "preflight")
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.verifier.verify_export(self.evidence, self.apks, self.env)
        for name, value in {"device-serial.txt": "emulator-5554\n", "qemu.txt": "1\n",
                            "api-level.txt": "30\n", "abi.txt": "x86_64\n",
                            "app-before.txt": "", "test-before.txt": "",
                            "source-install-app.txt": "Success\n", "source-install-test.txt": "Success\n"}.items():
            self.put(name, value)
        archive = b"KRALBAK1" + struct.pack(">III", 1, 3, 310_000) + bytes(28) + struct.pack(">I", 32) + bytes(32)
        (self.evidence / "kral-installation-backup.bin").write_bytes(archive)
        self.put("export-result.txt", self.phase_log("export"))
        result = self.verifier.verify_export(self.evidence, self.apks, self.env)
        self.assertEqual(result["validation_phase"], "export")
        self.assertNotIn("restore_verified", result)
        self.assertFalse((self.evidence / "backup-copy-result.json").exists())

        # Exercise the real phased CLI after reconstructing only the later fixture evidence.
        for name in ("source-uninstall-app", "source-uninstall-test", "target-install-app", "target-install-test"):
            self.put(name + ".txt", "Success\n")
        for name in ("app-between.txt", "test-between.txt"):
            self.put(name, "")
        self.put("restore-result.txt", self.phase_log("restore"))
        script = Path(__file__).resolve().parents[2] / "scripts/android_backup_copy_evidence.py"
        env = dict(os.environ, **self.env)
        output = self.evidence / "backup-copy-result.json"
        base = [sys.executable, str(script), str(self.evidence), str(self.apks)]
        for mode in ("--preflight", "--export-only"):
            result = subprocess.run(base + [mode], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(output.exists())
        result = subprocess.run(base, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(output.read_text())["restore_verified"])
        self.put("restore-result.txt", "OK (1 test)\nINSTRUMENTATION_CODE: -1\n")
        result = subprocess.run(base, env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
