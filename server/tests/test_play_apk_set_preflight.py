"""Synthetic device-profile APK extraction audit. No APKs or credentials real."""
import contextlib
import io
import json
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server import play_apk_set_preflight as a

ROOT = Path(__file__).resolve().parents[2]
SOURCE = dict(package="com.example.gptasistan.genesis",
              version_name="1.0.10-genesis-candidate",
              version_code=11, min_sdk=26, target_sdk=36, billing="9.1.0")
CERT = "1" * 64
BADGING = ("package: name='com.example.gptasistan.genesis' "
           "versionCode='11' versionName='1.0.10-genesis-candidate'\n"
           "sdkVersion:'26'\n"
           "targetSdkVersion:'36'\n")
SIGNING = "Signer #1 certificate SHA-256 digest: " + CERT + "\n"


class ApkSets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.set = self.root / "test.apks"
        self.profiles = self.root / "specs"
        self.extractions = self.root / "extracted"
        self.profiles.mkdir()
        self.extractions.mkdir()
        self.make_zip()
        self.prepare_profiles()

    def make_zip(self, rows=None):
        if rows is None:
            rows = {
                "toc.pb": b"fake-toc-data",
                "splits/base-master.apk": b"fake-apk-data",
                "splits/base-arm64_v8a.apk": b"fake-split-data",
            }
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.set, "w", zipfile.ZIP_DEFLATED) as z:
                for name, payload in (rows.items() if isinstance(rows, dict) else rows):
                    z.writestr(name, payload)

    def prepare_profiles(self):
        for key, spec in a.PROFILES.items():
            (self.profiles / (key + ".json")).write_text(
                json.dumps(spec), "utf-8")
            p = self.extractions / key
            p.mkdir()
            (p / "base-master.apk").write_bytes(b"mock APK bytes")
            (p / "base-arm64_v8a.apk").write_bytes(b"mock APK bytes")

    def runner(self, command, **kwargs):
        if command[0] == "apksigner":
            return SimpleNamespace(stdout=SIGNING)
        if command[0] == "aapt":
            if Path(command[-1]).name == "base-master.apk":
                return SimpleNamespace(stdout=BADGING)
            return SimpleNamespace(stdout=BADGING.replace(
                "versionName='1.0.10-genesis-candidate'",
                "versionName='1.0.10-genesis-candidate' split='config.arm64_v8a'"))
        raise AssertionError("UNEXPECTED_TOOL")

    def inspect(self):
        return a.run_preflight(
            repo_root=ROOT, apkset_path=self.set,
            profile_dir=self.profiles, extracts_root=self.extractions,
            aapt="aapt", apksigner="apksigner", runner=self.runner)

    def test_four_expected_profiles_are_distinct(self):
        self.assertEqual(set(a.PROFILES), {
            "api26-arm64", "api30-x86_64", "api36-arm64", "api36-x86_64"})
        self.assertEqual({v["sdkVersion"] for v in a.PROFILES.values()},
                         {26, 30, 36})

    def test_valid_synthetic_extractions_are_not_device_proof(self):
        proof = self.inspect()
        self.assertEqual(proof["device_profile_extractions"], "PASS")
        self.assertEqual(proof["real_device_installation"], "NOT_TESTED")
        self.assertEqual(proof["production"], "HOLD")
        self.assertFalse(proof["release_upload_ready"])

    def test_matching_apk_signature_in_all_profiles(self):
        self.assertEqual(self.inspect()["test_signer_sha256"], CERT)

    def test_sha256_apks_archive(self):
        from hashlib import sha256
        proof = self.inspect()
        self.assertEqual(proof["apk_set_sha256"],
                         sha256(self.set.read_bytes()).hexdigest())

    def test_no_play_release_certificate_claim(self):
        self.assertEqual(self.inspect()["signing_purpose"],
                         "EPHEMERAL_LOCAL_TEST_ONLY_NOT_PLAY")

    def test_no_toc_rejected(self):
        self.make_zip({"splits/base-master.apk": b"apk"})
        with self.assertRaisesRegex(a.ApkSetRejected, "STRUCTURE"):
            a.inspect_apks_archive(self.set)

    def test_no_apk_rejected(self):
        self.make_zip({"toc.pb": b"toc"})
        with self.assertRaisesRegex(a.ApkSetRejected, "STRUCTURE"):
            a.inspect_apks_archive(self.set)

    def test_duplicate_entries_rejected(self):
        self.make_zip([("toc.pb", b"one"), ("toc.pb", b"two"),
                       ("splits/base-master.apk", b"apk")])
        with self.assertRaisesRegex(a.ApkSetRejected, "DUPLICATE"):
            a.inspect_apks_archive(self.set)

    def test_path_traversal_rejected(self):
        self.make_zip({"toc.pb": b"toc", "splits/base-master.apk": b"apk",
                       "../exfiltrate": b"bad"})
        with self.assertRaisesRegex(a.ApkSetRejected, "UNSAFE"):
            a.inspect_apks_archive(self.set)

    def test_zip_size_cap(self):
        with patch.object(a, "MAX_APKSET_BYTES", 1):
            with self.assertRaisesRegex(a.ApkSetRejected, "SIZE"):
                a.inspect_apks_archive(self.set)

    def test_expansion_size_cap(self):
        with patch.object(a, "MAX_EXPANDED_BYTES", 1):
            with self.assertRaisesRegex(a.ApkSetRejected, "EXPANSION"):
                a.inspect_apks_archive(self.set)

    def test_invalid_zip_rejected(self):
        self.set.write_bytes(b"not-an-archive")
        with self.assertRaisesRegex(a.ApkSetRejected, "READ_FAILED"):
            a.inspect_apks_archive(self.set)

    def test_wrong_sdk_spec_rejected(self):
        path = self.profiles / "api26-arm64.json"
        spec = dict(a.PROFILES["api26-arm64"])
        spec["sdkVersion"] = 25
        path.write_text(json.dumps(spec), "utf-8")
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_SPEC_MISMATCH"):
            self.inspect()

    def test_injected_extra_profile_key_rejected(self):
        path = self.profiles / "api36-x86_64.json"
        spec = dict(a.PROFILES["api36-x86_64"])
        spec["fakeCompatible"] = True
        path.write_text(json.dumps(spec), "utf-8")
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_SPEC_MISMATCH"):
            self.inspect()

    def test_missing_profile_rejected(self):
        (self.profiles / "api30-x86_64.json").unlink()
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_FILE_MISSING"):
            self.inspect()

    def test_missing_extracted_profile_rejected(self):
        path = self.extractions / "api26-arm64"
        for file in path.glob("*.apk"):
            file.unlink()
        path.rmdir()
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_EXTRACTION_MISSING"):
            self.inspect()

    def test_empty_extracted_profile_rejected(self):
        for f in (self.extractions / "api26-arm64").glob("*.apk"):
            f.unlink()
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_APK_COUNT_INVALID"):
            self.inspect()

    def test_missing_real_base_manifest_rejected(self):
        (self.extractions / "api26-arm64" / "base-master.apk").unlink()
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_BASE_APK_MISSING"):
            self.inspect()

    def test_base_apk_renamed_but_manifest_still_detected(self):
        for key in a.PROFILES:
            p = self.extractions / key / "base-master.apk"
            p.rename(self.extractions / key / "primary-application.apk")
        def renamed(command, **kwargs):
            if command[0] == "aapt" and Path(command[-1]).name == "primary-application.apk":
                return SimpleNamespace(stdout=BADGING)
            return self.runner(command, **kwargs)
        proof = a.inspect_extractions(
            root=self.extractions, source=SOURCE,
            aapt="aapt", apksigner="apksigner", runner=renamed)
        self.assertEqual(len(proof["profiles"]), 4)

    def test_two_bases_manifest_ambiguity_denied(self):
        def two_bases(command, **kwargs):
            if command[0] == "aapt":
                return SimpleNamespace(stdout=BADGING)
            return self.runner(command, **kwargs)
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_BASE_APK_MISSING"):
            a.inspect_extractions(
                root=self.extractions, source=SOURCE,
                aapt="aapt", apksigner="apksigner", runner=two_bases)

    def test_wrong_package_aapt_rejected(self):
        def fake(command, **kwargs):
            response = self.runner(command, **kwargs)
            if command[0] == "aapt":
                return SimpleNamespace(stdout=BADGING.replace(
                    "com.example.gptasistan.genesis", "com.other.package"))
            return response
        with self.assertRaisesRegex(a.ApkSetRejected, "PACKAGE_MISMATCH"):
            a.inspect_extractions(root=self.extractions, source=SOURCE,
                aapt="aapt", apksigner="apksigner", runner=fake)

    def test_sdk_mismatch_rejected(self):
        def fake(command, **kwargs):
            if command[0] == "aapt":
                return SimpleNamespace(stdout=BADGING.replace(
                    "targetSdkVersion:'36'", "targetSdkVersion:'35'"))
            return self.runner(command, **kwargs)
        with self.assertRaisesRegex(a.ApkSetRejected, "SDK_MISMATCH"):
            a.inspect_extractions(root=self.extractions, source=SOURCE,
                aapt="aapt", apksigner="apksigner", runner=fake)

    def test_debuggable_release_rejected(self):
        def fake(command, **kwargs):
            if command[0] == "aapt":
                return SimpleNamespace(stdout=BADGING + "application-debuggable\n")
            return self.runner(command, **kwargs)
        with self.assertRaisesRegex(a.ApkSetRejected, "DEBUGGABLE"):
            a.inspect_extractions(root=self.extractions, source=SOURCE,
                aapt="aapt", apksigner="apksigner", runner=fake)

    def test_missing_signature_rejected(self):
        def fake(command, **kwargs):
            if command[0] == "apksigner":
                return SimpleNamespace(stdout="")
            return self.runner(command, **kwargs)
        with self.assertRaisesRegex(a.ApkSetRejected, "SIGNER_INVALID"):
            a.inspect_extractions(root=self.extractions, source=SOURCE,
                aapt="aapt", apksigner="apksigner", runner=fake)

    def test_cross_profile_signer_mismatch_denied(self):
        def fake(command, **kwargs):
            if command[0] == "apksigner" and "api36-arm64" in str(command[-1]):
                return SimpleNamespace(stdout=SIGNING.replace(CERT, "2" * 64))
            return self.runner(command, **kwargs)
        with self.assertRaisesRegex(a.ApkSetRejected, "SIGNER_CONFLICT"):
            a.inspect_extractions(root=self.extractions, source=SOURCE,
                aapt="aapt", apksigner="apksigner", runner=fake)

    def test_sdk_tool_failure_fails_closed(self):
        def fake(*args, **kwargs):
            raise FileNotFoundError("DO_NOT_LEAK_PATH")
        with self.assertRaisesRegex(a.ApkSetRejected, "ANDROID_SDK_INSPECTION_FAILED"):
            a.inspect_extractions(root=self.extractions, source=SOURCE,
                aapt="aapt", apksigner="apksigner", runner=fake)

    def test_boolean_profile_sdk_denied(self):
        spec = dict(a.PROFILES["api26-arm64"])
        spec["sdkVersion"] = True
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_SPEC_MISMATCH"):
            a.check_profile_json("api26-arm64", json.dumps(spec))

    def test_invalid_profile_json_denied(self):
        with self.assertRaisesRegex(a.ApkSetRejected, "PROFILE_JSON_INVALID"):
            a.check_profile_json("api26-arm64", "{broken")

    def test_profile_signer_script_does_not_claim_play_compliant(self):
        result = self.inspect()
        self.assertEqual(result["real_google_play_distribution"], "NOT_TESTED")
        self.assertEqual(result["android_emulator_execution"], "NOT_TESTED")

if __name__ == "__main__":
    unittest.main()
