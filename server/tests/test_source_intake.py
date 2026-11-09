"""Real local-file checks for fail-closed source intake."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout

from server import source_intake as intake


class SourceIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_zip(self, name, files):
        dest = self.root / name
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            for path, data in files:
                zipf.writestr(path, data)
        return dest

    def test_android_apk_static_inspection_preserves_original_bytes(self):
        path = self.make_zip("candidate.apk", [
            ("AndroidManifest.xml", b"binary-manifest-fixture"),
            ("classes.dex", b"dex" + b"\x00" * 64),
            ("lib/arm64-v8a/libsample.so", b"binary library"),
        ])
        original = path.read_bytes()
        result = intake.inspect_file(path)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(result["format"], "apk_candidate")
        self.assertEqual(result["sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(result["abi_paths_observed"], ["arm64-v8a"])
        self.assertEqual(result["source_status"], "ANALYZED_STATIC_ONLY")
        for flag in ("registered_as_capability", "external_api_called", "file_executed",
                     "file_extracted", "real_device_tested",
                     "signature_certificate_verified", "package_name_verified"):
            self.assertFalse(result[flag])
        self.assertEqual(set(self.root.iterdir()), {path})

    def test_aab_is_not_misidentified_as_installable_apk(self):
        p = self.make_zip("candidate.aab", [
            ("BundleConfig.pb", b"bundle"), ("base/manifest/AndroidManifest.xml", b"manifest")])
        self.assertEqual(intake.inspect_file(p)["format"], "aab_candidate")

    def test_apk_suffix_does_not_confer_apk_identity(self):
        p = self.make_zip("pretend.apk", [("README.txt", b"not executable")])
        self.assertEqual(intake.inspect_file(p)["format"], "zip_archive")

    def test_gguf_header_does_not_claim_usable_model(self):
        p = self.root / "weights.gguf"
        p.write_bytes(b"GGUF" + b"\x00" * 100)
        r = intake.inspect_file(p)
        self.assertEqual(r["format"], "gguf_header_candidate")
        self.assertFalse(r["runtime_verified"])
        self.assertFalse(r["model_weights_validated"])

    def test_pdf_is_not_executed(self):
        p = self.root / "source.pdf"
        p.write_bytes(b"%PDF-1.7\nfixture")
        r = intake.inspect_file(p)
        self.assertEqual(r["format"], "pdf_document")
        self.assertFalse(r["file_executed"])

    def test_reject_traversal_and_windows_archive_paths(self):
        for filename in ("../escape.txt", "/absolute/path", r"..\escape",
                         "C:/private/file", "sub/../escape", "same//file"):
            with self.subTest(filename=filename):
                p = self.make_zip("unsafe.zip", [(filename, b"x")])
                with self.assertRaisesRegex(intake.IntakeRejected, "ARCHIVE_UNSAFE_PATH"):
                    intake.inspect_file(p)
                self.assertEqual(set(self.root.iterdir()), {p})

    def test_reject_duplicate_entries(self):
        p = self.make_zip("duplicate.zip", [("a.txt", b"first"), ("a.txt", b"second")])
        with self.assertRaisesRegex(intake.IntakeRejected, "ARCHIVE_DUPLICATE_PATH"):
            intake.inspect_file(p)

    def test_reject_archive_symlinks(self):
        p = self.root / "archive.zip"
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(p, "w") as f:
            f.writestr(info, "../secret")
        with self.assertRaisesRegex(intake.IntakeRejected, "ARCHIVE_SPECIAL_ENTRY"):
            intake.inspect_file(p)

    def test_reject_decompression_bombs_without_extracting(self):
        p = self.make_zip("bomb.zip", [("big.txt", b"Z" * (1024 * 1024))])
        with self.assertRaisesRegex(intake.IntakeRejected, "ARCHIVE_COMPRESSION_BOMB"):
            intake.inspect_file(p)
        self.assertEqual(set(self.root.iterdir()), {p})

    def test_reject_unreadable_missing_or_empty_files(self):
        with self.assertRaises(intake.IntakeRejected):
            intake.inspect_file(self.root / "absent.apk")
        p = self.root / "empty.apk"
        p.write_bytes(b"")
        with self.assertRaisesRegex(intake.IntakeRejected, "SOURCE_SIZE_OUT_OF_BOUNDS"):
            intake.inspect_file(p)

    def test_never_follow_local_symlinks(self):
        p = self.root / "target.apk"
        p.write_bytes(b"ABC")
        link = self.root / "link.apk"
        link.symlink_to(p)
        with self.assertRaisesRegex(intake.IntakeRejected, "SOURCE_UNREADABLE_OR_SYMLINK"):
            intake.inspect_file(link)

    def test_cli_blocks_bad_files_without_printing_local_private_paths(self):
        import sys
        old = sys.argv
        out = io.StringIO()
        p = self.root / "missing.apk"
        try:
            sys.argv = ["source_intake", str(p)]
            with redirect_stdout(out):
                self.assertEqual(intake.main(), 2)
        finally:
            sys.argv = old
        report = json.loads(out.getvalue())
        self.assertEqual(report["results"][0]["error_code"], "SOURCE_UNREADABLE_OR_SYMLINK")
        self.assertEqual(report["live_capabilities_registered"], 0)
        self.assertNotIn(str(self.root), out.getvalue())


if __name__ == "__main__":
    unittest.main()
