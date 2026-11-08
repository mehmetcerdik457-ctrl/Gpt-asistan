"""Synthetic offline tests for ORBA Play preflight, with zero Google API access."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/orba_play_preflight.py"
spec = importlib.util.spec_from_file_location("orba_play_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class OrbaPlayPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "app/src/main").mkdir(parents=True)
        (self.root / "app/build.gradle.kts").write_text('''
android {
 defaultConfig {
  applicationId = "com.example.gptasistan.genesis"
  minSdk = 26
  targetSdk = 36
  versionCode = 11
  versionName = "1.0.10-genesis-candidate"
 }
 buildTypes { release { isDebuggable = false } }
}
''', encoding="utf-8")
        (self.root / "app/src/main/AndroidManifest.xml").write_text('''
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
 <uses-permission android:name="android.permission.INTERNET"/>
</manifest>
''', encoding="utf-8")

    def findings(self, **kwargs):
        return {a["control"]: a for a in preflight.inspect(self.root, **kwargs)["findings"]}

    def test_current_release_settings_recognized(self):
        f = self.findings()
        self.assertEqual(f["target_sdk"]["status"], "PASS")
        self.assertEqual(f["package_id"]["status"], "PASS")
        self.assertEqual(f["version"]["status"], "PASS")
        self.assertEqual(f["release_non_debuggable"]["status"], "PASS")

    def test_never_claims_money_or_play_approval(self):
        r = preflight.inspect(self.root)
        self.assertFalse(r["revenue_ready"])
        self.assertFalse(r["play_upload_approved"])
        self.assertTrue(all(x["status"] == "NOT_CHECKED" for x in r["external_evidence"]))

    def test_unsigned_missing_aab_blocked(self):
        self.assertEqual(self.findings()["signed_aab"]["status"], "BLOCKED")

    def test_low_sdk_blocked(self):
        p = self.root / "app/build.gradle.kts"
        p.write_text(p.read_text().replace("targetSdk = 36", "targetSdk = 34"))
        self.assertEqual(self.findings()["target_sdk"]["status"], "BLOCKED")

    def test_ads_missing_not_approved(self):
        self.assertEqual(self.findings()["admob_sdk"]["status"], "NOT_IMPLEMENTED")

    def test_ads_present_still_not_revenue_ready(self):
        p = self.root / "app/build.gradle.kts"
        p.write_text(p.read_text() + '\nimplementation("com.google.android.gms:play-services-ads:25.0.0")\n')
        self.assertEqual(self.findings()["admob_sdk"]["status"], "SOURCE_PRESENT")
        self.assertFalse(preflight.inspect(self.root)["revenue_ready"])

    def test_billing_is_not_mandatory_for_paid_download(self):
        f = self.findings()
        self.assertEqual(f["play_billing_sdk"]["status"], "NOT_IMPLEMENTED")
        self.assertIn("does not bar", f["play_billing_sdk"]["evidence"])

    def test_non_debuggable_required(self):
        p = self.root / "app/build.gradle.kts"
        p.write_text(p.read_text().replace("isDebuggable = false", "isDebuggable = true"))
        self.assertEqual(self.findings()["release_non_debuggable"]["status"], "BLOCKED")

    def test_no_manifest_or_gradle_reports_error(self):
        (self.root / "app/src/main/AndroidManifest.xml").unlink()
        with self.assertRaises(ValueError):
            preflight.inspect(self.root)

    def test_fake_aab_rejected(self):
        bundle = self.root / "test.aab"
        bundle.write_bytes(b"not a signed jar")
        status = self.findings(aab=bundle)["signed_aab"]
        self.assertEqual(status["status"], "BLOCKED")
        self.assertIn("aab_sha256=", status["evidence"])

    def test_external_checks_stay_unverified_even_with_signed_jar_mock(self):
        bundle = self.root / "test.aab"
        bundle.write_bytes(b"dummy")
        with patch.object(preflight.subprocess, "run", return_value=subprocess.CompletedProcess([],0,"jar verified.\n", "")):
            report = preflight.inspect(self.root, aab=bundle)
        f = {x["control"]:x for x in report["findings"]}
        self.assertEqual(f["signed_aab"]["status"], "JAR_VERIFIED")
        self.assertFalse(report["play_upload_approved"])

    def test_strict_exit_blocked(self):
        self.assertEqual(preflight.main(["--repo-root", str(self.root), "--strict"]), 2)


if __name__ == "__main__":
    unittest.main()
