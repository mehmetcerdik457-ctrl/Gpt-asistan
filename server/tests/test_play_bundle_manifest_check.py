"""Synthetic merged-manifest tests; no Google Play or external jar required."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from server import play_bundle_manifest_check as m
from server.play_distribution_preflight import source_from_repo

ROOT = Path(__file__).resolve().parents[2]
SOURCE = source_from_repo(ROOT)
XML = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
 package="com.example.gptasistan.genesis"
 android:versionCode="11" android:versionName="1.0.10-genesis-candidate">
 <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="36" />
 <uses-permission android:name="android.permission.INTERNET" />
 <application android:debuggable="false"
              android:allowBackup="false"
              android:usesCleartextTraffic="false" />
</manifest>"""


class DecodedBundleTests(unittest.TestCase):
    def accept(self, xml=XML):
        return m.inspect_manifest(xml, SOURCE)

    def rejects(self, message, xml):
        with self.assertRaisesRegex(m.BundleManifestRejected, message):
            m.inspect_manifest(xml, SOURCE)

    def test_good_decoded_manifest_passes_but_release_holds(self):
        result = self.accept()
        self.assertEqual(result["decoded_bundle_manifest"], "PASS")
        self.assertEqual(result["production"], "HOLD")
        self.assertFalse(result["release_upload_ready"])

    def test_real_source_consistency(self):
        self.assertEqual(self.accept()["release_variant_package"],
                         "com.example.gptasistan.genesis")

    def test_unverified_play_signing(self):
        self.assertEqual(self.accept()["upload_and_app_signing"], "NOT_VERIFIED")

    def test_no_claim_of_live_payments(self):
        self.assertEqual(self.accept()["live_payments"], "NOT_TESTED")

    def test_wrong_package_rejected(self):
        self.rejects("PACKAGE_MISMATCH",
                     XML.replace("com.example.gptasistan.genesis", "com.attacker.fake"))

    def test_wrong_version_code_rejected(self):
        self.rejects("VERSION_CODE_MISMATCH",
                     XML.replace('versionCode="11"', 'versionCode="12"'))

    def test_missing_version_code_rejected(self):
        self.rejects("VERSION_CODE_MISMATCH",
                     XML.replace('android:versionCode="11"', ""))

    def test_wrong_version_name_rejected(self):
        self.rejects("VERSION_NAME_MISMATCH",
                     XML.replace('1.0.10-genesis-candidate', '1.0.9'))

    def test_wrong_min_sdk_rejected(self):
        self.rejects("SDK_BOUND_MISMATCH",
                     XML.replace('minSdkVersion="26"', 'minSdkVersion="25"'))

    def test_wrong_target_sdk_rejected(self):
        self.rejects("SDK_BOUND_MISMATCH",
                     XML.replace('targetSdkVersion="36"', 'targetSdkVersion="35"'))

    def test_missing_sdk_denied(self):
        self.rejects("SDK_DECLARATION",
                     XML.replace('<uses-sdk android:minSdkVersion="26" android:targetSdkVersion="36" />', ''))

    def test_duplicate_sdk_denied(self):
        self.rejects("SDK_DECLARATION",
                     XML.replace('<uses-sdk', '<uses-sdk android:name="dummy"')
                     .replace('</manifest>', ' <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="36" /></manifest>'))

    def test_debuggable_true_denied(self):
        self.rejects("DEBUGGABLE", XML.replace('debuggable="false"', 'debuggable="true"'))

    def test_implicit_non_debuggable_allowed(self):
        self.assertEqual(self.accept(XML.replace('android:debuggable="false"', ''))["production"],
                         "HOLD")

    def test_cleartext_enabled_denied(self):
        self.rejects("SECURITY_FLAGS", XML.replace('usesCleartextTraffic="false"',
                                                   'usesCleartextTraffic="true"'))

    def test_backups_enabled_denied(self):
        self.rejects("SECURITY_FLAGS", XML.replace('allowBackup="false"',
                                                   'allowBackup="true"'))

    def test_missing_internet_denied(self):
        self.rejects("INTERNET_PERMISSION", XML.replace(
            'android.permission.INTERNET', 'android.permission.WIFI_STATE'))

    def test_multiple_applications_denied(self):
        self.rejects("APPLICATION_AMBIGUOUS", XML.replace(
            '</manifest>', '<application /></manifest>'))

    def test_malformed_xml_denied(self):
        self.rejects("DECODE_INVALID", "<manifest")

    def test_empty_xml_denied(self):
        self.rejects("SIZE_INVALID", "")

    def test_external_doctype_denied(self):
        self.rejects("EXTERNAL_ENTITY", '<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///secrets">]>' + XML)

    def test_manifest_size_limit(self):
        self.rejects("SIZE_INVALID", XML + " " * m.MAX_MANIFEST_BYTES)

    def test_invalid_source_identity_fails_closed(self):
        with self.assertRaisesRegex(m.BundleManifestRejected, "SOURCE_IDENTITY"):
            m.inspect_manifest(XML, {})

    def test_cli_reports_hold_with_valid_decoded_xml(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "dump.xml"
            f.write_text(XML, encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = m.main(["--repo-root", str(ROOT), "--decoded-manifest", str(f)])
            self.assertEqual(rc, 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["production"], "HOLD")
            self.assertEqual(data["decoded_bundle_manifest"], "PASS")

    def test_cli_invalid_xml_never_returns_success(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "dump.xml"
            f.write_text("<manifest", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = m.main(["--repo-root", str(ROOT), "--decoded-manifest", str(f)])
            self.assertEqual(rc, 1)
            self.assertEqual(json.loads(out.getvalue())["production"], "HOLD")

    def test_cli_missing_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = m.main(["--repo-root", str(ROOT),
                             "--decoded-manifest", str(Path(folder) / "missing")])
            self.assertEqual(rc, 1)

if __name__ == "__main__":
    unittest.main()
