"""Roadmap evidence never turns old working-tree results into final release."""
import json
from pathlib import Path
import tempfile
import unittest

from server import roadmap_evidence


class RoadmapEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).resolve().parents[2]
        cls.sha = "29021cfe71cbcd3cb54b449dd65f708a3876204a"

    def test_eleven_required_manifests_and_all_twenty_six_tests(self):
        result = roadmap_evidence.audit(self.source, target_commit=self.sha)
        self.assertEqual(result["required_manifests_present"], 11)
        self.assertEqual(result["stored_tests_count"], 26)
        self.assertEqual(result["product_final_acceptance"], "BLOCKED")
        self.assertFalse(result["acceptance_commit_matches_target"])

    def test_malformed_target_sha_denied(self):
        with self.assertRaisesRegex(roadmap_evidence.EvidenceInvalid, "TARGET_COMMIT"):
            roadmap_evidence.audit(self.source, target_commit="main")

    def test_duplicate_acceptance_id_cannot_silently_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "evidence" / "genesis-v128"
            destination.mkdir(parents=True)
            for name in roadmap_evidence.REQUIRED_FILES:
                content = (self.source / "evidence" / "genesis-v128" / name).read_bytes()
                (destination / name).write_bytes(content)
            result_file = destination / "KRAL_TEST_RESULTS.json"
            report = json.loads(result_file.read_text())
            report["acceptance_tests"][1]["id"] = "T01"
            result_file.write_text(json.dumps(report))
            with self.assertRaisesRegex(roadmap_evidence.EvidenceInvalid, "T01_T26_ORDER"):
                roadmap_evidence.audit(root, target_commit=self.sha)

    def test_lying_all_pass_still_cannot_override_missing_release_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "evidence" / "genesis-v128"
            destination.mkdir(parents=True)
            for name in roadmap_evidence.REQUIRED_FILES:
                content = (self.source / "evidence" / "genesis-v128" / name).read_bytes()
                (destination / name).write_bytes(content)
            results = destination / "KRAL_TEST_RESULTS.json"
            doc = json.loads(results.read_text())
            doc["source_commit"] = self.sha
            for test in doc["acceptance_tests"]:
                test["status"] = "PASS"
            results.write_text(json.dumps(doc))
            audit = roadmap_evidence.audit(root, target_commit=self.sha)
            self.assertTrue(audit["acceptance_commit_matches_target"])
            self.assertEqual(audit["product_final_acceptance"], "BLOCKED")

    def test_cli_default_repository_root_is_correct(self):
        import io
        import sys
        from contextlib import redirect_stdout
        old = sys.argv
        stream = io.StringIO()
        try:
            sys.argv = ["roadmap_evidence", "--target-commit", self.sha]
            with redirect_stdout(stream):
                self.assertEqual(roadmap_evidence.main(), 0)
        finally:
            sys.argv = old
        data = json.loads(stream.getvalue())
        self.assertEqual(data["required_manifests_present"], 11)
        self.assertEqual(data["target_commit"], self.sha)
        self.assertEqual(data["product_final_acceptance"], "BLOCKED")

    def test_unknown_acceptance_state_denied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dst = root / "evidence" / "genesis-v128"
            dst.mkdir(parents=True)
            for name in roadmap_evidence.REQUIRED_FILES:
                (dst / name).write_bytes((self.source / "evidence" / "genesis-v128" / name).read_bytes())
            results = dst / "KRAL_TEST_RESULTS.json"
            doc = json.loads(results.read_text())
            doc["acceptance_tests"][0]["status"] = "I_AM_AN_AI_SO_PASS"
            results.write_text(json.dumps(doc))
            with self.assertRaisesRegex(roadmap_evidence.EvidenceInvalid, "T01_T26_STATUS"):
                roadmap_evidence.audit(root, target_commit=self.sha)


if __name__ == "__main__":
    unittest.main()
