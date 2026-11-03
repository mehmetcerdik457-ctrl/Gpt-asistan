"""Regression tests: mismatched APK identity never passes upgrade acceptance."""
import subprocess
import unittest
from unittest.mock import patch

from scripts.check_android_upgrade import (
    ApkIdentity,
    UpgradeRejected,
    _tool_output,
    parse_badging,
    parse_signing_certificates,
    verify_upgrade,
)

FINGERPRINT_A = "a" * 64
FINGERPRINT_B = "b" * 64


class AndroidUpgradeGateTests(unittest.TestCase):
    def old(self):
        return ApkIdentity("com.example.gptasistan.genesis", 4, FINGERPRINT_A, True)

    def new(self):
        return ApkIdentity("com.example.gptasistan.genesis", 5, FINGERPRINT_A, False)

    def test_valid_upgrade_requires_strictly_newer_version_and_same_signer(self):
        verify_upgrade(self.old(), self.new(), require_release=True)

    def test_changed_package_is_blocked(self):
        with self.assertRaisesRegex(UpgradeRejected, "APK_PACKAGE_ID_CHANGED"):
            verify_upgrade(
                self.old(),
                ApkIdentity("com.example.gptasistan", 5, FINGERPRINT_A, False),
            )

    def test_changed_signer_is_blocked(self):
        with self.assertRaisesRegex(UpgradeRejected, "APK_SIGNER_CERT_CHANGED"):
            verify_upgrade(
                self.old(),
                ApkIdentity("com.example.gptasistan.genesis", 5, FINGERPRINT_B, False),
            )

    def test_equal_version_is_blocked(self):
        with self.assertRaisesRegex(UpgradeRejected, "APK_VERSION_CODE_NOT_INCREASED"):
            verify_upgrade(
                self.old(),
                ApkIdentity("com.example.gptasistan.genesis", 4, FINGERPRINT_A, False),
            )

    def test_downgrade_is_blocked(self):
        with self.assertRaisesRegex(UpgradeRejected, "APK_VERSION_CODE_NOT_INCREASED"):
            verify_upgrade(
                self.old(),
                ApkIdentity("com.example.gptasistan.genesis", 3, FINGERPRINT_A, False),
            )

    def test_debuggable_release_candidate_is_blocked(self):
        with self.assertRaisesRegex(UpgradeRejected, "CANDIDATE_IS_DEBUGGABLE"):
            verify_upgrade(
                self.old(),
                ApkIdentity("com.example.gptasistan.genesis", 5, FINGERPRINT_A, True),
                require_release=True,
            )

    def test_parse_android_sdk_badging(self):
        output = (
            "package: name='com.example.gptasistan.genesis' versionCode='5' versionName='1.0.5'\n"
            "sdkVersion:'26'\ntargetSdkVersion:'36'\n"
            "application-debuggable\n"
        )
        self.assertEqual(
            ("com.example.gptasistan.genesis", 5, True),
            parse_badging(output),
        )

    def test_parse_missing_or_multiple_packages_fails_closed(self):
        with self.assertRaisesRegex(UpgradeRejected, "PACKAGE_METADATA"):
            parse_badging("application-label:'KRAL'")
        one = "package: name='com.example.gptasistan.genesis' versionCode='5' versionName='x'\n"
        with self.assertRaisesRegex(UpgradeRejected, "PACKAGE_METADATA"):
            parse_badging(one + one)

    def test_parse_signer_sha_normalized(self):
        output = "Signer #1 certificate SHA-256 digest: " + ":".join(["AB"] * 32)
        self.assertEqual("ab" * 32, parse_signing_certificates(output))

    def test_missing_or_multiple_signers_fail_closed(self):
        with self.assertRaisesRegex(UpgradeRejected, "APK_SIGNER_MISSING"):
            parse_signing_certificates("Verified using v3 scheme (APK Signature Scheme v3): true")
        with self.assertRaisesRegex(UpgradeRejected, "APK_SIGNER_MISSING"):
            parse_signing_certificates(
                f"Signer #1 certificate SHA-256 digest: {FINGERPRINT_A}\n"
                f"Signer #2 certificate SHA-256 digest: {FINGERPRINT_B}\n"
            )

    def test_invalid_signature_fingerprint_fails_closed(self):
        with self.assertRaisesRegex(UpgradeRejected, "APK_SIGNER_CERT_SHA256_INVALID"):
            parse_signing_certificates("Signer #1 certificate SHA-256 digest: abc\n")

    def test_missing_sdk_tool_fails_closed(self):
        with patch("scripts.check_android_upgrade.subprocess.run", side_effect=OSError("no aapt")):
            with self.assertRaisesRegex(UpgradeRejected, "ANDROID_SDK_TOOL_FAILED"):
                _tool_output(["aapt", "dump", "badging", "something.apk"])

    def test_sdk_tool_verification_failure_fails_closed(self):
        with patch(
            "scripts.check_android_upgrade.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["apksigner", "verify"]),
        ):
            with self.assertRaisesRegex(UpgradeRejected, "ANDROID_SDK_TOOL_FAILED"):
                _tool_output(["apksigner", "verify", "something.apk"])


if __name__ == "__main__":
    unittest.main()
