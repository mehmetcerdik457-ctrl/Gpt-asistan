import importlib.util
from pathlib import Path
import tempfile
import unittest


def module(name):
    path = Path(__file__).resolve().parents[2] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class DeliveryEvidenceTests(unittest.TestCase):
    def test_real_xml_counts_keep_skips_separate_and_reject_failures(self):
        evidence = module("android_delivery_evidence")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = root / "TEST-example.xml"
            lint = root / "lint.xml"
            tests.write_text('<testsuite tests="5" failures="0" errors="0" skipped="2"/>')
            lint.write_text('<issues><issue severity="Warning"/></issues>')
            result = evidence.summarize(root, lint)
            self.assertEqual(result["unit_tests_passed"], 3)
            self.assertEqual(result["unit_tests"]["skipped"], 2)
            self.assertEqual(result["lint"]["severities"], {"Warning": 1})
            tests.write_text('<testsuite tests="5" failures="1"/>')
            with self.assertRaisesRegex(ValueError, "UNIT_TESTS_NOT_PASSED"):
                evidence.summarize(root, lint)

    def test_missing_test_results_and_lint_errors_never_report_success(self):
        evidence = module("android_delivery_evidence")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lint = root / "lint.xml"
            lint.write_text('<issues><issue severity="Error"/></issues>')
            with self.assertRaisesRegex(ValueError, "UNIT_TEST_RESULTS_MISSING"):
                evidence.summarize(root, lint)
            (root / "TEST-example.xml").write_text('<testsuite tests="1"/>')
            with self.assertRaisesRegex(ValueError, "LINT_ERRORS_PRESENT"):
                evidence.summarize(root, lint)

    def test_recognizable_credentials_detected_without_echoing_values(self):
        scanner = module("check_delivery_secrets")
        fixtures = [(b"sk-" + b"A" * 32, "OPENAI_STYLE_KEY"),
                    (b"ghp_" + b"B" * 36, "GITHUB_TOKEN"),
                    (b"AIza" + b"C" * 35, "GOOGLE_API_KEY"),
                    (b"-----BEGIN " + b"PRIVATE KEY-----", "PRIVATE_KEY_PEM")]
        for value, rule in fixtures:
            self.assertEqual(scanner.rules_matched(value), [rule])
        self.assertEqual(scanner.rules_matched(b'OPENAI_API_KEY=os.environ["OPENAI_API_KEY"]'), [])
