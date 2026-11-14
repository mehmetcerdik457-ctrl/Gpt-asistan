"""Offline unsigned AAB layout and release-HOLD security contract tests."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from server import play_bundle_preflight as p

REQUIRED = {
    "BundleConfig.pb": b"synthetic_bundle_config",
    "base/manifest/AndroidManifest.xml": b"synthetic_proto_manifest",
    "base/resources.pb": b"synthetic_resources",
    "base/dex/classes.dex": b"dex\x0a035\x00",
}


class BundlePreflightTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "candidate.aab"

    def build(self, files=None):
        if files is None:
            files = REQUIRED
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                if isinstance(files, dict):
                    files = list(files.items())
                for name, content in files:
                    z.writestr(name, content)
        return self.path

    def check(self, files=None):
        return p.inspect_bundle(self.build(files))

    def fails(self, error, files):
        with self.assertRaisesRegex(p.BundlePreflightDenied, error):
            self.check(files)

    def test_complete_unsigned_bundle_is_structural_pass(self):
        report = self.check()
        self.assertEqual(report["structure"], "PASS")
        self.assertEqual(report["production"], "HOLD")
        self.assertFalse(report["release_upload_ready"])

    def test_unsigned_candidate_not_play_signed(self):
        report = self.check()
        self.assertEqual(report["play_console_signing"], "NOT_VERIFIED")
        self.assertEqual(report["signature"], "UNSIGNED_CONFIRMED_BY_ARCHIVE_MARKERS")

    def test_bundle_sha_matches_actual_binary(self):
        self.build()
        self.assertEqual(p.inspect_bundle(self.path)["bundle_sha256"],
                         hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_no_product_catalog_or_live_payment_claims(self):
        report = self.check()
        self.assertEqual(report["play_console_product_catalog"], "NOT_VERIFIED")
        self.assertEqual(report["real_google_play_payment"], "NOT_TESTED")

    def test_bundle_manifest_not_claimed_decoded(self):
        self.assertEqual(self.check()["android_bundle_manifest_package"],
                         "NOT_DECODED")

    def test_missing_bundle_config_rejected(self):
        d = dict(REQUIRED)
        del d["BundleConfig.pb"]
        self.fails("REQUIRED_STRUCTURE", d)

    def test_missing_manifest_rejected(self):
        d = dict(REQUIRED)
        del d["base/manifest/AndroidManifest.xml"]
        self.fails("REQUIRED_STRUCTURE", d)

    def test_missing_resources_rejected(self):
        d = dict(REQUIRED)
        del d["base/resources.pb"]
        self.fails("REQUIRED_STRUCTURE", d)

    def test_missing_dex_rejected(self):
        d = dict(REQUIRED)
        del d["base/dex/classes.dex"]
        self.fails("DEX_MISSING", d)

    def test_split_dex_accepted(self):
        d = dict(REQUIRED)
        del d["base/dex/classes.dex"]
        d["base/dex/classes2.dex"] = b"valid"
        self.assertEqual(self.check(d)["structure"], "PASS")

    def test_signed_rsa_rejected_not_mistaken_for_release_ready(self):
        self.fails("UNEXPECTED_BUNDLE_SIGNATURE",
                   {**REQUIRED, "META-INF/CERT.RSA": b"signature"})

    def test_signed_ec_rejected(self):
        self.fails("UNEXPECTED_BUNDLE_SIGNATURE",
                   {**REQUIRED, "META-INF/SIGNER.EC": b"signature"})

    def test_signed_sf_rejected(self):
        self.fails("UNEXPECTED_BUNDLE_SIGNATURE",
                   {**REQUIRED, "META-INF/CERT.SF": b"signature"})

    def test_meta_inf_regular_metadata_allowed(self):
        report = self.check({**REQUIRED,
                             "META-INF/com/android/build/gradle/app-metadata.properties":
                             b"gradle"})
        self.assertEqual(report["structure"], "PASS")

    def test_duplicate_file_names_rejected(self):
        self.fails("DUPLICATE_ENTRY",
                   list(REQUIRED.items()) + [("BundleConfig.pb", b"different")])

    def test_archive_path_traversal_rejected(self):
        self.fails("UNSAFE_ENTRY",
                   {**REQUIRED, "base/../../steal": b"malicious"})

    def test_absolute_archive_name_rejected(self):
        self.fails("UNSAFE_ENTRY",
                   {**REQUIRED, "/etc/secret": b"malicious"})

    def test_backslash_archive_name_rejected(self):
        self.fails("UNSAFE_ENTRY",
                   {**REQUIRED, r"base\..\secret": b"malicious"})

    def test_zero_byte_bundle_rejected(self):
        self.path.write_bytes(b"")
        with self.assertRaisesRegex(p.BundlePreflightDenied, "SIZE_INVALID"):
            p.inspect_bundle(self.path)

    def test_invalid_zip_rejected_without_internal_path_leak(self):
        self.path.write_bytes(b"not zip")
        with self.assertRaisesRegex(p.BundlePreflightDenied, "READ_OR_INTEGRITY"):
            p.inspect_bundle(self.path)

    def test_bundle_size_cap_fails_closed(self):
        self.build()
        with patch.object(p, "MAX_AAB_BYTES", 50):
            with self.assertRaisesRegex(p.BundlePreflightDenied, "SIZE_INVALID"):
                p.inspect_bundle(self.path)

    def test_archive_uncompressed_cap_fails_closed(self):
        self.build()
        with patch.object(p, "MAX_UNCOMPRESSED_BYTES", 10):
            with self.assertRaisesRegex(p.BundlePreflightDenied, "EXPANSION_LIMIT"):
                p.inspect_bundle(self.path)

    def test_archive_file_count_cap_fails_closed(self):
        self.build()
        with patch.object(p, "MAX_FILES", 2):
            with self.assertRaisesRegex(p.BundlePreflightDenied, "ENTRIES_INVALID"):
                p.inspect_bundle(self.path)

    def test_cannot_request_signed_release_using_unsigned_preflight(self):
        self.build()
        with self.assertRaisesRegex(p.BundlePreflightDenied, "UNSIGNED_CI_POLICY"):
            p.inspect_bundle(self.path, require_unsigned=False)

    def test_no_bundle_file_is_not_accepted(self):
        with self.assertRaisesRegex(p.BundlePreflightDenied, "READ_OR_INTEGRITY"):
            p.inspect_bundle(self.path)

    def test_cli_structural_pass_still_hold(self):
        self.build()
        out = io.StringIO()
        root = Path(__file__).resolve().parents[2]
        with contextlib.redirect_stdout(out):
            code = p.main(["--repo-root", str(root), "--bundle", str(self.path)])
        self.assertEqual(code, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["production"], "HOLD")
        self.assertFalse(report["release_upload_ready"])
        self.assertEqual(report["source_application_id"],
                         "com.example.gptasistan.genesis")

    def test_cli_broken_aab_reports_failure_and_hold(self):
        self.path.write_bytes(b"broken")
        out = io.StringIO()
        root = Path(__file__).resolve().parents[2]
        with contextlib.redirect_stdout(out):
            code = p.main(["--repo-root", str(root), "--bundle", str(self.path)])
        self.assertEqual(code, 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report["production"], "HOLD")
        self.assertEqual(report["structure"], "FAIL")


if __name__ == "__main__":
    unittest.main()
