"""Release verification must reject unsigned bundles and conflicting manifests."""
import base64
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import android_release_artifact as release


def vi(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def pb(number, value):
    if isinstance(value, int):
        return vi(number << 3) + vi(value)
    if isinstance(value, str):
        value = value.encode()
    return vi((number << 3) | 2) + vi(len(value)) + value


def attr(name, value, *, android=True, compiled=None):
    result = pb(2, name) + pb(3, value)
    if android:
        result += pb(1, release.ANDROID_NS)
    if compiled is not None:
        result += pb(6, pb(7, compiled))
    return pb(4, result)


def node(name, attrs=b"", children=()):
    return pb(1, pb(3, name) + attrs + b"".join(pb(5, child) for child in children))


def manifest(*, debug=False, extra_application=False):
    attrs = (attr("package", release.PACKAGE, android=False) + attr("versionCode", "8")
             + attr("versionName", "1.0.7-genesis-candidate"))
    application = node("application", attr("debuggable", "false", compiled=pb(8, int(debug))))
    children = [node("uses-sdk", attr("minSdkVersion", "26", compiled=pb(6, 26))
                     + attr("targetSdkVersion", "36", compiled=pb(6, 36))), application]
    if extra_application:
        children.append(application)
    return node("manifest", attrs, children)


class ReleaseManifestTests(unittest.TestCase):
    def test_reads_aapt2_xml_manifest_and_uses_compiled_boolean(self):
        result = release.bundle_manifest(manifest())
        self.assertEqual(result, {"package": release.PACKAGE, "version_code": 8,
                                  "version_name": "1.0.7-genesis-candidate", "min_sdk": 26,
                                  "target_sdk": 36, "debuggable": False})
        self.assertTrue(release.bundle_manifest(manifest(debug=True))["debuggable"])

    def test_truncated_manifest_and_duplicate_elements_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "TRUNCATED"):
            release.bundle_manifest(manifest()[:-1])
        with self.assertRaisesRegex(ValueError, "ELEMENTS_INVALID"):
            release.bundle_manifest(manifest(extra_application=True))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FIELD"):
            release.bundle_manifest(manifest() + manifest())

    def test_validates_native_abis_and_dex_without_extracting_archive_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / "release.aab"
            with zipfile.ZipFile(bundle, "w") as archive:
                archive.writestr("base/manifest/AndroidManifest.xml", manifest())
                archive.writestr("base/dex/classes.dex", b"fixture bytecode")
                for abi in release.ABIS:
                    archive.writestr(f"base/lib/{abi}/libfixture.so", b"fixture native lib")
            abis, dex, actual = release.archive_content(bundle, bundle=True)
            self.assertEqual(abis, release.ABIS)
            self.assertEqual(dex, {"classes.dex": hashlib.sha256(b"fixture bytecode").hexdigest()})
            self.assertFalse(actual["debuggable"])


class ReleaseBundleSignatureTests(unittest.TestCase):
    def setUp(self):
        self.cert = b"synthetic public certificate fixture"
        self.digest = hashlib.sha256(self.cert).hexdigest()
        self.pem = ("Signer #1:\nCertificate #1:\n-----BEGIN CERTIFICATE-----\n"
                    + base64.b64encode(self.cert).decode() + "\n-----END CERTIFICATE-----\n")

    def test_pinned_self_signed_certificate_warning_is_allowed(self):
        verified = subprocess.CompletedProcess([], 4, stdout="\njar verified.\n", stderr="")
        with patch.object(release.subprocess, "run", return_value=verified), patch.object(release, "command", return_value=self.pem):
            release.verify_bundle_signature(Path("fixture.aab"), self.digest)

    def test_unsigned_entries_and_missing_verified_marker_are_rejected(self):
        for status, output in ((16, "jar verified."), (20, "jar verified."), (0, "jar is unsigned.")):
            with self.subTest(status=status, output=output):
                result = subprocess.CompletedProcess([], status, stdout=output, stderr="")
                with patch.object(release.subprocess, "run", return_value=result), self.assertRaisesRegex(ValueError, "SIGNATURE_INVALID"):
                    release.verify_bundle_signature(Path("fixture.aab"), self.digest)

    def test_unexpected_signer_and_multiple_signers_are_rejected(self):
        verified = subprocess.CompletedProcess([], 0, stdout="jar verified.\n", stderr="")
        for certificates, expected_error in ((self.pem, "PIN_MISMATCH"),
                                              (self.pem + "Signer #2:\n", "SIGNER_AMBIGUOUS")):
            with patch.object(release.subprocess, "run", return_value=verified), patch.object(release, "command", return_value=certificates):
                with self.assertRaisesRegex(ValueError, expected_error):
                    release.verify_bundle_signature(Path("fixture.aab"), "0" * 64)
