import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class AndroidBackupPolicyTests(unittest.TestCase):
    def test_manifest_explicitly_disables_backup_and_references_rules(self):
        manifest = ET.parse(ROOT / "app/src/main/AndroidManifest.xml").getroot()
        application = manifest.find("application")
        self.assertIsNotNone(application)
        self.assertEqual(application.get(ANDROID_NS + "allowBackup"), "false")
        self.assertEqual(application.get(ANDROID_NS + "dataExtractionRules"), "@xml/data_extraction_rules")
        self.assertEqual(application.get(ANDROID_NS + "fullBackupContent"), "@xml/backup_rules")

    def test_android_12_cloud_and_device_transfer_exclude_private_files(self):
        rules = ET.parse(ROOT / "app/src/main/res/xml/data_extraction_rules.xml").getroot()
        self.assertEqual(rules.tag, "data-extraction-rules")
        for mode in ("cloud-backup", "device-transfer"):
            with self.subTest(mode=mode):
                section = rules.find(mode)
                self.assertIsNotNone(section)
                excludes = {(item.get("domain"), item.get("path")) for item in section.findall("exclude")}
                self.assertIn(("root", "."), excludes)

    def test_legacy_full_backup_excludes_private_files(self):
        rules = ET.parse(ROOT / "app/src/main/res/xml/backup_rules.xml").getroot()
        self.assertEqual(rules.tag, "full-backup-content")
        excludes = {(item.get("domain"), item.get("path")) for item in rules.findall("exclude")}
        self.assertIn(("root", "."), excludes)


if __name__ == "__main__":
    unittest.main()
