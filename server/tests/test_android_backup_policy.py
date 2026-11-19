"""Fail-closed checks for Android owner-data backup and transfer policy.

Static policy checks only; not a device backup/restore test.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "app" / "src" / "main" / "res" / "xml"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class AndroidOwnerBackupPolicyTests(unittest.TestCase):
    def test_manifest_denies_backup_and_cleartext_and_names_explicit_rules(self):
        root = ET.parse(ROOT / "app" / "src" / "main" / "AndroidManifest.xml").getroot()
        app = root.find("application")
        self.assertIsNotNone(app)
        self.assertEqual(app.get(ANDROID_NS + "allowBackup"), "false")
        self.assertEqual(app.get(ANDROID_NS + "usesCleartextTraffic"), "false")
        self.assertEqual(app.get(ANDROID_NS + "dataExtractionRules"), "@xml/data_extraction_rules")
        self.assertEqual(app.get(ANDROID_NS + "fullBackupContent"), "@xml/backup_rules")

    def test_cloud_and_device_transfer_both_exclude_all_app_files(self):
        root = ET.parse(RES / "data_extraction_rules.xml").getroot()
        self.assertEqual(root.tag, "data-extraction-rules")
        for section_name in ("cloud-backup", "device-transfer"):
            with self.subTest(section=section_name):
                section = root.find(section_name)
                self.assertIsNotNone(section)
                self.assertFalse(section.findall("include"))
                self.assertIn(
                    ("root", "."),
                    {(entry.get("domain"), entry.get("path")) for entry in section.findall("exclude")},
                )

    def test_legacy_backup_excludes_all_app_files(self):
        root = ET.parse(RES / "backup_rules.xml").getroot()
        self.assertEqual(root.tag, "full-backup-content")
        self.assertFalse(root.findall("include"))
        self.assertIn(
            ("root", "."),
            {(entry.get("domain"), entry.get("path")) for entry in root.findall("exclude")},
        )


if __name__ == "__main__":
    unittest.main()
