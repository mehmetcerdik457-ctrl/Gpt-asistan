"""Build-time evidence: KRAL/CİHAT preview cannot replace existing Genesis APK.

The old 1.0.4 package has a distinct signing certificate from the GitHub
1.0.3 candidate. A parallel debug namespace protects both installations
and their separate private databases. This is NOT a device upgrade test.
"""
import unittest
from pathlib import Path

from scripts.android_artifact import PREVIEW_PACKAGE, verify_preview_package

ROOT = Path(__file__).resolve().parents[2]


class AndroidPreviewNamespaceTests(unittest.TestCase):
    def test_expected_preview_package_is_accepted(self):
        verify_preview_package(PREVIEW_PACKAGE, PREVIEW_PACKAGE)

    def test_previous_installed_packages_are_never_accepted(self):
        for actual in (
            "com.example.gptasistan.genesis",
            "com.example.gptasistan.candidate",
            "com.example.gptasistan",
            "com.codespaceapps.aichat",
            "com.example.gptasistan.genesis.cihatpreview.copy",
        ):
            with self.subTest(actual=actual), self.assertRaisesRegex(ValueError, "APK_PACKAGE_MISMATCH"):
                verify_preview_package(actual, PREVIEW_PACKAGE)

    def test_wrong_expected_package_cannot_bypass_policy(self):
        for expected in (
            "com.example.gptasistan.genesis",
            "com.example.gptasistan.genesis.cihatpreview.test",
            "com.codespaceapps.aichat",
            "",
        ):
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, "APK_PACKAGE_POLICY_DENIED"):
                verify_preview_package(expected, expected)

    def test_gradle_debug_build_has_separate_app_id(self):
        contents = (ROOT / "app/build.gradle.kts").read_text()
        self.assertIn('applicationId = "com.example.gptasistan"', contents)
        self.assertIn('applicationIdSuffix = ".genesis.cihatpreview"', contents)
        self.assertNotIn('applicationIdSuffix = ".genesis"', contents)
        self.assertIn('versionName = "1.0.3-genesis-cihat-preview"', contents)

    def test_delivery_and_emulator_are_bound_to_same_package(self):
        workflow = (ROOT / ".github/workflows/android.yml").read_text()
        smoke = (ROOT / "scripts/android_emulator_smoke.sh").read_text()
        self.assertIn("--expected-package " + PREVIEW_PACKAGE, workflow)
        self.assertIn("package=" + PREVIEW_PACKAGE, smoke)
        self.assertIn("metadata['package'] == '" + PREVIEW_PACKAGE + "'", smoke)
        self.assertNotIn("package=com.example.gptasistan.genesis\n", smoke)

    def test_launcher_is_visibly_marked_preview(self):
        strings = (ROOT / "app/src/debug/res/values/strings.xml").read_text()
        self.assertIn("KRAL CİHAT Önizleme", strings)
        manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()
        self.assertIn('android:label="@string/app_name"', manifest)

if __name__ == "__main__":
    unittest.main()
