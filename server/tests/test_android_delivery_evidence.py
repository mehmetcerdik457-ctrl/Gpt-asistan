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
            tests.write_text('<testsuite tests="5" failures="0" errors="0" skipped="2">'
                             '<testcase classname="Store" name="a"><skipped/></testcase>'
                             '<testcase classname="Store" name="b"><skipped/></testcase>'
                             '<testcase classname="Store" name="c"/>'
                             '<testcase classname="Store" name="d"/>'
                             '<testcase classname="Store" name="e"/></testsuite>')
            lint.write_text('<issues><issue severity="Warning"/></issues>')
            result = evidence.summarize(root, lint)
            self.assertEqual(result["unit_tests_passed"], 3)
            self.assertEqual(result["unit_tests"]["skipped"], 2)
            self.assertEqual([case["name"] for case in result["skipped_tests"]], ["a", "b"])
            self.assertEqual(result["lint"]["severities"], {"Warning": 1})
            tests.write_text('<testsuite tests="1" failures="1">'
                             '<testcase classname="Store" name="a"><failure/></testcase></testsuite>')
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
            (root / "TEST-example.xml").write_text('<testsuite tests="1">'
                                                  '<testcase classname="Store" name="a"/></testsuite>')
            with self.assertRaisesRegex(ValueError, "LINT_ERRORS_PRESENT"):
                evidence.summarize(root, lint)

    def test_truncated_counts_hidden_failures_and_invalid_identities_are_rejected(self):
        evidence = module("android_delivery_evidence")
        fixtures = [
            ('<testsuite tests="2"><testcase classname="Store" name="a"/></testsuite>',
             "UNIT_TEST_COUNT_MISMATCH"),
            ('<testsuite tests="1"><testcase classname="Store" name="a"><failure/></testcase></testsuite>',
             "UNIT_TEST_COUNT_MISMATCH"),
            ('<testsuite tests="1"><testcase name="a"/></testsuite>', "UNIT_TEST_IDENTITY_MISSING"),
            ('<testsuite tests="2"><testcase classname="Store" name="a"/>'
             '<testcase classname="Store" name="a"/></testsuite>', "UNIT_TEST_IDENTITY_DUPLICATE"),
            ('<testsuite tests="1" skipped="1" failures="1"><testcase classname="Store" name="a">'
             '<skipped/><failure/></testcase></testsuite>', "UNIT_TEST_OUTCOME_INVALID"),
            ('<testsuite tests="-1"/>', "UNIT_TEST_COUNTS_INVALID"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lint = root / "lint.xml"
            lint.write_text('<issues/>')
            for xml, error in fixtures:
                with self.subTest(error=error, xml=xml):
                    (root / "TEST-example.xml").write_text(xml)
                    with self.assertRaisesRegex(ValueError, error):
                        evidence.summarize(root, lint)

    def test_duplicate_report_files_cannot_double_count_executed_tests(self):
        evidence = module("android_delivery_evidence")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lint = root / "lint.xml"
            lint.write_text('<issues/>')
            xml = '<testsuite tests="1"><testcase classname="Store" name="a"/></testsuite>'
            (root / "TEST-first.xml").write_text(xml)
            (root / "TEST-copy.xml").write_text(xml)
            with self.assertRaisesRegex(ValueError, "UNIT_TEST_IDENTITY_DUPLICATE"):
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
