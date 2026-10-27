"""Delivery gate tests with synthetic ZIPs and mocked Android tool output.

These tests do not compile, install, or cryptographically verify an Android APK.
Real apksigner verification remains required by the production delivery command.
"""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import android_artifact as artifact


PACKAGE = "com.example.gptasistan.genesis"
SIGNER = "a1" * 32
SIGNATURE = f"Signer #1 certificate SHA-256 digest: {SIGNER}\n"


def badging(*, package=PACKAGE, debug=True, split=False):
    split_flag = " split='config.en'" if split else ""
    return (
        "Synthetic aapt fixture; not a real APK inspection\n"
        f"package: name='{package}' versionCode='4' versionName='1.0.3-genesis-candidate'{split_flag}\n"
        "sdkVersion:'26'\n"
        "targetSdkVersion:'34'\n"
        "uses-permission: name='android.permission.INTERNET'\n"
        + ("application-debuggable\n" if debug else "")
    )


class CandidateIdentityTests(unittest.TestCase):
    def check(self, manifest=None, signature=SIGNATURE, signer=None, release=False):
        return artifact.candidate_identity(manifest or badging(), signature, PACKAGE, signer, release)

    def test_existing_debug_candidate_is_accepted_without_release_identity_claim(self):
        result = self.check()
        self.assertEqual(result["package"], PACKAGE)
        self.assertEqual(result["artifact_type"], "debug_candidate")
        self.assertFalse(result["signer_reference_matched"])

    def test_original_application_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unexpected candidate package"):
            self.check(badging(package="com.example.gptasistan"))

    def test_other_candidate_id_is_not_silently_substituted(self):
        with self.assertRaisesRegex(ValueError, "Unexpected candidate package"):
            self.check(badging(package="com.example.gptasistan.candidate"))

    def test_split_is_rejected_even_when_package_line_is_not_first(self):
        with self.assertRaisesRegex(ValueError, "split APK"):
            self.check(badging(split=True))

    def test_release_requires_explicit_full_signer_reference(self):
        with self.assertRaisesRegex(ValueError, "requires --expected-signer-sha256"):
            self.check(badging(debug=False))

    def test_pinned_non_debuggable_candidate_is_accepted(self):
        result = self.check(badging(debug=False), signer=SIGNER.upper(), release=True)
        self.assertEqual(result["artifact_type"], "release_candidate")
        self.assertEqual(result["signer_certificate_sha256"], [SIGNER])
        self.assertTrue(result["signer_reference_matched"])

    def test_debug_candidate_cannot_be_labelled_release_even_with_matching_pin(self):
        with self.assertRaisesRegex(ValueError, "debuggable APK"):
            self.check(signer=SIGNER, release=True)

    def test_wrong_or_additional_signer_is_rejected(self):
        for signature in (
            "Signer #1 certificate SHA-256 digest: " + "b2" * 32 + "\n",
            SIGNATURE + "Signer #2 certificate SHA-256 digest: " + "b2" * 32 + "\n",
        ):
            with self.subTest(signature=signature), self.assertRaisesRegex(ValueError, "expected single signer"):
                self.check(badging(debug=False), signature=signature, signer=SIGNER)

    def test_absent_or_malformed_tool_certificate_is_rejected(self):
        for signature in ("", "Signer #1 certificate SHA-256 digest: a1...a1\n"):
            with self.subTest(signature=signature), self.assertRaisesRegex(ValueError, "valid signing certificate"):
                self.check(signature=signature)

    def test_shortened_reference_is_not_a_signer_pin(self):
        with self.assertRaisesRegex(ValueError, "exactly 64 hexadecimal"):
            self.check(badging(debug=False), signer="a1...a1")


class ArtifactDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.apk = self.root / "synthetic-test-fixture.apk"
        with zipfile.ZipFile(self.apk, "w") as archive:
            archive.writestr("test-fixture.txt", "Not an installable APK; delivery gate fixture only.")
        self.output = self.root / "delivery"

    def run_delivery(self, manifest=None, signature_error=False, extra=()):
        def tool_command(*args):
            if Path(args[0]).name == "aapt":
                return manifest or badging()
            if Path(args[0]).name == "apksigner":
                if signature_error:
                    raise subprocess.CalledProcessError(1, args)
                return SIGNATURE
            if args == ("git", "rev-parse", "HEAD"):
                return "1" * 40 + "\n"
            if args == ("git", "branch", "--show-current"):
                return "synthetic-test-branch\n"
            if args == ("git", "status", "--porcelain"):
                return ""
            raise AssertionError(f"Unexpected fixture command: {args}")

        argv = ["android_artifact.py", str(self.apk), str(self.output), "--sdk", str(self.root / "sdk"), *extra]
        with patch("sys.argv", argv), patch.object(artifact, "command", side_effect=tool_command), redirect_stdout(io.StringIO()):
            artifact.main()

    def test_default_cli_preserves_debug_flow_and_records_exact_file_hash(self):
        self.run_delivery()
        result = json.loads((self.output / "apk-metadata.json").read_text())
        self.assertEqual(result["expected_package"], PACKAGE)
        self.assertEqual(result["sha256"], hashlib.sha256(self.apk.read_bytes()).hexdigest())
        self.assertNotEqual(result["sha256"], result["signer_certificate_sha256"][0])
        self.assertFalse(result["signer_reference_matched"])
        self.assertFalse(result["physical_device_tested"])
        self.assertFalse(result["emulator_tested"])
        self.assertFalse(result["live_model_tested"])

    def test_wrong_package_does_not_publish_success_metadata(self):
        with self.assertRaises(ValueError):
            self.run_delivery(badging(package="com.example.gptasistan"))
        self.assertFalse(self.output.exists())

    def test_unsigned_or_invalid_signature_does_not_publish_success_metadata(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_delivery(signature_error=True)
        self.assertFalse(self.output.exists())

    def test_non_debuggable_artifact_without_pin_does_not_publish_success_metadata(self):
        with self.assertRaises(ValueError):
            self.run_delivery(badging(debug=False))
        self.assertFalse(self.output.exists())

    def test_pinned_release_cli_records_reference_match(self):
        self.run_delivery(badging(debug=False), extra=("--release", "--expected-signer-sha256", SIGNER))
        result = json.loads((self.output / "apk-metadata.json").read_text())
        self.assertEqual(result["artifact_type"], "release_candidate")
        self.assertTrue(result["signer_reference_matched"])


if __name__ == "__main__":
    unittest.main()
