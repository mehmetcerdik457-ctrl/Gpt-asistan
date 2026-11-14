"""Package drift, compiled debug signer, and production-HOLD contract tests."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from server import play_distribution_preflight as preflight


class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.root = root
        cls.gradle = (root / "app/build.gradle.kts").read_text("utf-8")
        cls.manifest = (root / "app/src/main/AndroidManifest.xml").read_text("utf-8")
        cls.packages = dict.fromkeys(
            ("entitlement", "api", "acknowledge", "rtdn", "voided"),
            "com.example.gptasistan.genesis")
        cls.source = preflight.source_from_repo(root)
        cls.badging = (
            "package: name='com.example.gptasistan.genesis' "
            "versionCode='11' versionName='1.0.10-genesis-candidate'\n"
            "sdkVersion:'26'\n"
            "targetSdkVersion:'36'\n"
            "application-debuggable\n")
        cls.signer = ("Signer #1 certificate SHA-256 digest: "
                      + "a" * 64 + "\n")

    def inspect(self, gradle=None, manifest=None, packages=None):
        return preflight.source_identity(
            self.gradle if gradle is None else gradle,
            self.manifest if manifest is None else manifest,
            self.packages if packages is None else packages)

    def test_current_source_packages_align(self):
        self.assertEqual(self.source["package"],
                         "com.example.gptasistan.genesis")

    def test_version_code_is_positive(self):
        self.assertGreater(self.source["version_code"], 0)

    def test_android_sdk_order_valid(self):
        self.assertLessEqual(self.source["min_sdk"], self.source["target_sdk"])

    def test_gradle_package_drift_rejected(self):
        bad = self.gradle.replace(
            'applicationId = "com.example.gptasistan.genesis"',
            'applicationId = "com.wrong.application"')
        with self.assertRaisesRegex(preflight.PreflightDenied, "PACKAGE_MISMATCH"):
            self.inspect(gradle=bad)

    def test_server_package_drift_rejected(self):
        p = dict(self.packages)
        p["rtdn"] = "com.wrong.app"
        with self.assertRaisesRegex(preflight.PreflightDenied, "PACKAGE_MISMATCH"):
            self.inspect(packages=p)

    def test_duplicate_gradle_package_rejected(self):
        with self.assertRaisesRegex(preflight.PreflightDenied, "PACKAGE_AMBIGUOUS"):
            self.inspect(gradle=self.gradle + '\napplicationId = "fake.app"\n')

    def test_missing_play_billing_dependency_rejected(self):
        bad=self.gradle.replace("com.android.billingclient:billing:9.1.0",
                                "com.android.billingclient:other:9.1.0")
        with self.assertRaisesRegex(preflight.PreflightDenied, "BILLING_VERSION"):
            self.inspect(gradle=bad)

    def test_insecure_cleartext_manifest_rejected(self):
        bad=self.manifest.replace('android:usesCleartextTraffic="false"',
                                  'android:usesCleartextTraffic="true"')
        with self.assertRaisesRegex(preflight.PreflightDenied, "UNSAFE"):
            self.inspect(manifest=bad)

    def test_backup_enabled_rejected(self):
        bad=self.manifest.replace('android:allowBackup="false"',
                                  'android:allowBackup="true"')
        with self.assertRaisesRegex(preflight.PreflightDenied, "UNSAFE"):
            self.inspect(manifest=bad)

    def test_no_internet_permission_rejected(self):
        bad=self.manifest.replace('android.permission.INTERNET',
                                  'android.permission.OTHER')
        with self.assertRaisesRegex(preflight.PreflightDenied, "INTERNET"):
            self.inspect(manifest=bad)

    def test_invalid_xml_rejected(self):
        with self.assertRaisesRegex(preflight.PreflightDenied, "MANIFEST_INVALID"):
            self.inspect(manifest="<manifest")

    def test_target_exceeds_compile_rejected(self):
        bad=self.gradle.replace("targetSdk = 36", "targetSdk = 99")
        with self.assertRaisesRegex(preflight.PreflightDenied, "BUILD_POLICY"):
            self.inspect(gradle=bad)

    def test_negative_version_rejected(self):
        bad=self.gradle.replace("versionCode = 11", "versionCode = 0")
        with self.assertRaisesRegex(preflight.PreflightDenied, "BUILD_POLICY"):
            self.inspect(gradle=bad)

    def test_valid_compiled_debug_package_and_signer(self):
        proof=preflight.debug_apk_identity(
            self.badging, self.signer, self.source)
        self.assertEqual(proof["kind"], "DEBUG_APK")
        self.assertEqual(proof["debug_certificate_sha256"], "a" * 64)

    def test_compiled_package_mismatch_denied(self):
        bad=self.badging.replace("com.example.gptasistan.genesis", "com.fake.app")
        with self.assertRaisesRegex(preflight.PreflightDenied, "APK_PACKAGE"):
            preflight.debug_apk_identity(bad,self.signer,self.source)

    def test_compiled_version_code_mismatch_denied(self):
        bad=self.badging.replace("versionCode='11'", "versionCode='12'")
        with self.assertRaisesRegex(preflight.PreflightDenied, "APK_PACKAGE"):
            preflight.debug_apk_identity(bad,self.signer,self.source)

    def test_compiled_version_name_mismatch_denied(self):
        bad=self.badging.replace("1.0.10-genesis-candidate", "bad")
        with self.assertRaises(preflight.PreflightDenied):
            preflight.debug_apk_identity(bad,self.signer,self.source)

    def test_compiled_sdk_mismatch_denied(self):
        bad=self.badging.replace("targetSdkVersion:'36'", "targetSdkVersion:'34'")
        with self.assertRaisesRegex(preflight.PreflightDenied, "APK_SDK"):
            preflight.debug_apk_identity(bad,self.signer,self.source)

    def test_no_debuggability_proof_denied(self):
        bad=self.badging.replace("application-debuggable", "")
        with self.assertRaisesRegex(preflight.PreflightDenied, "DEBUG_ARTIFACT"):
            preflight.debug_apk_identity(bad,self.signer,self.source)

    def test_missing_signer_certificate_denied(self):
        with self.assertRaisesRegex(preflight.PreflightDenied, "SIGNATURE"):
            preflight.debug_apk_identity(self.badging, "", self.source)

    def test_wrong_signer_digest_length_denied(self):
        with self.assertRaisesRegex(preflight.PreflightDenied, "SIGNATURE"):
            preflight.debug_apk_identity(
                self.badging,
                "Signer #1 certificate SHA-256 digest: bad\n", self.source)

    def test_source_pass_always_production_hold(self):
        report=preflight.hold_report(self.source)
        self.assertEqual(report["production"], "HOLD")
        self.assertEqual(report["play_console_package"], "NOT_VERIFIED")

    def test_debug_apk_pass_always_production_hold(self):
        report=preflight.hold_report(self.source,
            preflight.debug_apk_identity(
                self.badging,self.signer,self.source))
        self.assertEqual(report["built_debug_apk_consistency"], "PASS")
        self.assertEqual(report["production"], "HOLD")
        self.assertEqual(report["play_app_signing"], "NOT_VERIFIED")

    def test_cli_unverified_source_succeeds_only_as_hold(self):
        output=io.StringIO()
        with redirect_stdout(output):
            status=preflight.main(["--repo-root",str(self.root)])
        self.assertEqual(status,0)
        self.assertEqual(json.loads(output.getvalue())["production"],"HOLD")

    def test_cli_wrong_expected_console_package_fails(self):
        output=io.StringIO()
        with redirect_stdout(output):
            status=preflight.main(["--repo-root",str(self.root),
                "--expected-play-package","com.other.app"])
        self.assertEqual(status,1)
        self.assertEqual(json.loads(output.getvalue())["check"],"FAIL")

    def test_cli_partial_apk_evidence_fails(self):
        output=io.StringIO()
        with redirect_stdout(output):
            status=preflight.main(["--repo-root",str(self.root),
                "--apk-badging", "missing-file"])
        self.assertEqual(status,1)
        self.assertEqual(json.loads(output.getvalue())["production"],"HOLD")

if __name__ == "__main__":
    unittest.main()
