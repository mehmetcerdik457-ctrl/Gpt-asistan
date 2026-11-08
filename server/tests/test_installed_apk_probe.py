"""Pure simulated regression coverage; never contacts an Android device."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import subprocess
import unittest
from unittest.mock import patch

from scripts.check_android_upgrade import ApkIdentity, UpgradeRejected
from scripts.inspect_installed_apk import (
    checked_serial, checked_package, parse_pm_paths, probe, run_adb,
)

PACKAGE = "com.example.gptasistan.genesis"
CERT = "a" * 64
OTHER_CERT = "b" * 64


class InstalledApkProbeTests(unittest.TestCase):
    def test_single_base_is_allowed(self):
        self.assertEqual(("/data/app/sample/base.apk",), parse_pm_paths("package:/data/app/sample/base.apk\n"))

    def test_split_paths_preserve_all_apks(self):
        result = parse_pm_paths("package:/data/app/sample/base.apk\npackage:/data/app/sample/split_config.arm64_v8a.apk\n")
        self.assertEqual(2, len(result))

    def test_empty_or_non_package_data_is_rejected(self):
        for raw in ("", "Error: package not found", "package:/foo.txt", "package:relative/base.apk"):
            with self.subTest(raw=raw), self.assertRaises(UpgradeRejected):
                parse_pm_paths(raw)

    def test_duplicate_or_missing_base_rejected(self):
        for raw in ("package:/foo/a.apk", "package:/foo/base.apk\npackage:/foo/base.apk\n", "package:/foo/base.apk\npackage:/bar/base.apk\n"):
            with self.subTest(raw=raw), self.assertRaises(UpgradeRejected):
                parse_pm_paths(raw)

    def test_untrusted_remote_paths_blocked(self):
        for raw in ("package:/data/app/../base.apk", "package:/data/app/my base.apk", "package:/data/app//base.apk", "package:/data/app/base.apk\nDEBUG"):
            with self.subTest(raw=raw), self.assertRaises(UpgradeRejected):
                parse_pm_paths(raw)

    def test_bad_serial_and_package_fail_closed(self):
        for raw in ("", "--foo", "serial with spaces", "a" * 129):
            with self.subTest(raw=raw), self.assertRaises(UpgradeRejected):
                checked_serial(raw)
        for raw in ("", "no-dot", "com.example;rm", "com..example"):
            with self.subTest(raw=raw), self.assertRaises(UpgradeRejected):
                checked_package(raw)

    def test_adb_failure_never_leaks_details(self):
        with patch("scripts.inspect_installed_apk.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["adb"], stderr="secret")):
            with self.assertRaisesRegex(UpgradeRejected, "ADB_READ_ONLY_COMMAND_FAILED"):
                run_adb(["adb", "devices"])

    def fake_adb(self, args, timeout=60):
        if "shell" in args:
            return "package:/data/app/id/base.apk\npackage:/data/app/id/split_config.arm64_v8a.apk\n"
        if "pull" in args:
            Path(args[-1]).write_bytes(b"synthetic APK, never device data")
            return "pulled"
        raise AssertionError("Unexpected adb call")

    def fake_inspect(self, path, **kwargs):
        return ApkIdentity(PACKAGE, 10, CERT, False)

    def test_read_only_baseline_reports_limits(self):
        with patch("scripts.inspect_installed_apk.run_adb", side_effect=self.fake_adb), patch("scripts.inspect_installed_apk.inspect_apk", side_effect=self.fake_inspect):
            report = probe(serial="emulator-5554", package=PACKAGE)
        self.assertEqual("INSTALLED_APK_IDENTITY_OBSERVED_NOT_UPGRADE_APPROVAL", report["status"])
        self.assertEqual(1, report["installed_split_apk_count"])
        self.assertFalse(report["upgrade_performed"])
        self.assertFalse(report["database_migration_verified"])
        self.assertFalse(report["device_owner_verified"])

    def test_split_identity_mismatch_blocks(self):
        n = iter([ApkIdentity(PACKAGE, 10, CERT, False), ApkIdentity(PACKAGE, 10, OTHER_CERT, False)])
        with patch("scripts.inspect_installed_apk.run_adb", side_effect=self.fake_adb), patch("scripts.inspect_installed_apk.inspect_apk", side_effect=lambda *a, **k: next(n)):
            with self.assertRaisesRegex(UpgradeRejected, "INSTALLED_SPLIT_IDENTITY_MISMATCH"):
                probe(serial="emulator-5554", package=PACKAGE)

    def test_wrong_owner_cert_blocks(self):
        with patch("scripts.inspect_installed_apk.run_adb", side_effect=self.fake_adb), patch("scripts.inspect_installed_apk.inspect_apk", side_effect=self.fake_inspect):
            with self.assertRaisesRegex(UpgradeRejected, "INSTALLED_OWNER_CERT_MISMATCH"):
                probe(serial="emulator-5554", package=PACKAGE, expected_owner_cert_sha256=OTHER_CERT)

    def test_missing_pair_is_blocked_before_adb(self):
        with patch("scripts.inspect_installed_apk.run_adb", side_effect=AssertionError("must not adb")):
            with self.assertRaisesRegex(UpgradeRejected, "CANDIDATE_AND_PIN"):
                probe(serial="emulator-5554", package=PACKAGE, candidate=Path("some.apk"))

    def test_matching_nondebuggable_candidate_is_only_metadata_proof(self):
        with TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate.apk"
            candidate.write_bytes(b"synthetic newer candidate")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            def fake_inspect(path, **kwargs):
                return ApkIdentity(PACKAGE, 11 if path == candidate else 10, CERT, False)
            with patch("scripts.inspect_installed_apk.run_adb", side_effect=self.fake_adb), patch("scripts.inspect_installed_apk.inspect_apk", side_effect=fake_inspect):
                report = probe(serial="emulator-5554", package=PACKAGE,
                               candidate=candidate, expected_candidate_sha256=digest,
                               expected_owner_cert_sha256=CERT)
            self.assertEqual("APK_IDENTITIES_COMPATIBLE_NOT_INSTALLATION_PROOF", report["status"])
            self.assertFalse(report["upgrade_performed"])

    def test_debug_candidate_is_rejected(self):
        with TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "candidate.apk"
            candidate.write_bytes(b"synthetic debug")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            def fake_inspect(path, **kwargs):
                return ApkIdentity(PACKAGE, 11 if path == candidate else 10, CERT, path == candidate)
            with patch("scripts.inspect_installed_apk.run_adb", side_effect=self.fake_adb), patch("scripts.inspect_installed_apk.inspect_apk", side_effect=fake_inspect):
                with self.assertRaisesRegex(UpgradeRejected, "CANDIDATE_IS_DEBUGGABLE"):
                    probe(serial="emulator-5554", package=PACKAGE,
                          candidate=candidate, expected_candidate_sha256=digest)


if __name__ == "__main__":
    unittest.main()
