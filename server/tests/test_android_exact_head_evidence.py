"""Prove PR candidate workflows verify the *actual* head, not GitHub PR merge ref."""
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
EXACT="github.event.pull_request.head.sha || github.sha"

class AndroidExactHeadEvidenceTest(unittest.TestCase):
    def test_android_build_and_emulator_checkout_exact_head(self):
        w=(ROOT/".github/workflows/android.yml").read_text()
        self.assertEqual(w.count(f"ref: ${{{{ {EXACT} }}}}"),2)
        self.assertEqual(w.count("KRAL_EXACT_HEAD_SHA=$actual"),2)
        self.assertEqual(w.count('test "$actual" = "$expected"'),2)
        self.assertEqual(w.count("persist-credentials: false"),2)

    def test_emulator_uses_git_head_from_checked_out_repo_not_pr_merge_ref(self):
        s=(ROOT/"scripts/android_emulator_smoke.sh").read_text()
        self.assertNotIn("os.environ['GITHUB_SHA']",s)
        self.assertEqual(s.count("os.environ['KRAL_EXACT_HEAD_SHA']"),2)
        self.assertIn("'physical_phone_tested': False",s)
        self.assertIn("'live_model_tested': False",s)

    def test_python_ci_has_same_exact_ref(self):
        w=(ROOT/".github/workflows/ci.yml").read_text()
        self.assertIn(f"ref: ${{{{ {EXACT} }}}}",w)
        self.assertIn("KRAL_PYTHON_EXACT_HEAD=PASS",w)

if __name__ == "__main__":
    unittest.main()
