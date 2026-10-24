"""Offline, no-cost regression tests for owner-approved Copilot dispatcher."""
import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from server import mission_control as mc
from server import mission_dispatch as disp


REPO = "mehmetcerdik457-ctrl/Gpt-asistan"
OTHER = "mehmetcerdik457-ctrl/benim-uygulamam"


def fixture():
    return {"schema": 1, "owner": mc.REPOSITORY_OWNER, "worker_slots": 50,
            "max_parallel": 4, "tasks": [{
                "id": "T001", "repo": REPO, "role": "code-reviewer",
                "title": "Check code", "description": "Review the fixed scoped source, return test evidence.",
                "depends_on": [], "paths": ["server/"]}]}


class DispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repos = mc.validate_repository_inventory(mc.read_small_json(mc.REPO_INVENTORY))

    def proposal(self, manifest=None, branch="integration/safe-20261025"):
        return disp.proposal(fixture() if manifest is None else manifest,
                             self.repos, "T001", branch)

    def test_preview_is_a_dry_run(self):
        s = self.proposal()
        self.assertEqual(s["repo"], REPO)
        self.assertEqual(s["api_request"]["assignees"], [disp.BOT])
        self.assertEqual(s["api_request"]["agent_assignment"]["custom_agent"], "")
        self.assertIn("code-reviewer", s["issue_body"])
        self.assertNotIn("main", s["base_branch"])

    def test_default_cli_never_accesses_network_or_logs_task_body(self):
        with patch.object(disp.mission, "read_small_json", side_effect=[
            {"owner": "mehmetcerdik457-ctrl", "repositories": [
                "Gpt-asistan", "benim-uygulamam"]}, fixture()
            ]), patch.object(disp, "submit_one", side_effect=AssertionError("NO NETWORK")):
            # Does not need a real file; read_small_json is mocked.
            result = disp.main(["fake.json", "--task", "T001",
                                "--branch", "integration/safe-20261025"])
            self.assertEqual(result, 0)

    def test_main_and_untrusted_branch_blocked(self):
        for branch in ["main", "master", "copilot/x", "integration/../main",
                       "integration//x", "integration/", "security/x.", "http://evil",
                       "feature/my-test"]:
            with self.subTest(branch=branch), self.assertRaises(mc.MissionRejected):
                self.proposal(branch=branch)

    def test_secrets_and_hostile_descriptions_rejected(self):
        for secret in ["ghp_" + "a"*30, "github_pat_" + "X"*30,
                       "sk-" + "a"*32, "https://user:passwd@example.com", "-----BEGIN PRIVATE KEY-----"]:
            manifest = fixture()
            manifest["tasks"][0]["description"] += " " + secret
            with self.subTest(secret=secret[:6]), self.assertRaises(mc.MissionRejected):
                self.proposal(manifest)

    def test_nonexistent_and_dependent_task_blocked(self):
        obj = fixture()
        obj["tasks"].append({**copy.deepcopy(obj["tasks"][0]), "id": "T002", "depends_on": ["T001"]})
        with self.assertRaisesRegex(mc.MissionRejected, "DEPENDENCY"):
            disp.proposal(obj, self.repos, "T002", "integration/safe-20261025")
        with self.assertRaisesRegex(mc.MissionRejected, "TASK_NOT_IN"):
            disp.proposal(obj, self.repos, "T999", "integration/safe-20261025")

    def test_dispatch_requires_verified_branch_and_no_duplicate_issue(self):
        s = self.proposal()
        with patch.object(disp, "_request", return_value={"name": "main"}):
            with self.assertRaisesRegex(mc.MissionRejected, "BRANCH_NOT_VERIFIED"):
                disp.submit_one(s, "dummy")
        with patch.object(disp, "_request", side_effect=[
            {"name": s["base_branch"]},
            [{"body": s["dedup_marker"], "number": 22}],
        ]):
            with self.assertRaisesRegex(mc.MissionRejected, "ALREADY_SUBMITTED"):
                disp.submit_one(s, "dummy")
        with patch.object(disp, "_request", side_effect=[
            {"name": s["base_branch"]}, [{}]*100
        ]):
            with self.assertRaisesRegex(mc.MissionRejected, "NOT_COMPLETE"):
                disp.submit_one(s, "dummy")

    def test_only_one_owner_approved_issue_can_be_submitted(self):
        s = self.proposal()
        with patch.object(disp, "_request", side_effect=[
            {"name": s["base_branch"]},
            [],
            {"number": 82, "state": "open"},
        ]) as request:
            result = disp.submit_one(s, "user-to-server-token-test-fixture")
        self.assertEqual(result["status"], "ISSUE_CREATED_AGENT_NOT_VERIFIED")
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args.args[1], "issues")
        self.assertEqual(request.call_args.args[3], "POST")
        self.assertEqual(request.call_args.args[4]["assignees"], [disp.BOT])

    def test_github_api_does_not_allow_redirect_or_unsafe_endpoints(self):
        with self.assertRaises(mc.MissionRejected):
            disp.NoRedirect().redirect_request(None, None, 302, "", {},
                                               "https://malicious.example")
        for endpoint in ["../user", "secrets", "issues/1/comments", "branches/main", "branches/integration/../main"]:
            with self.subTest(endpoint=endpoint), self.assertRaises(mc.MissionRejected):
                disp._request(REPO, endpoint, "dummy")
        with self.assertRaises(mc.MissionRejected):
            disp._request(OTHER, "issues", "")

    def test_cli_execute_refuses_actions_token_or_missing_approval(self):
        inventory = {"owner": "mehmetcerdik457-ctrl",
                     "repositories": ["Gpt-asistan", "benim-uygulamam"]}
        args = ["fake.json", "--task", "T001", "--branch", "integration/safe-20261025", "--execute"]
        with patch.object(disp.mission, "read_small_json", side_effect=[inventory, fixture()]), \
             patch.object(disp, "submit_one", side_effect=AssertionError("SHOULD NOT RUN")):
            self.assertEqual(disp.main(args), 2)
        with patch.object(disp.mission, "read_small_json", side_effect=[inventory, fixture()]), \
             patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "KRAL_COPILOT_USER_TOKEN": "dummy"}, clear=True), \
             patch.object(disp, "submit_one", side_effect=AssertionError("SHOULD NOT RUN")):
            self.assertEqual(disp.main(args + ["--owner-approved", "--public-issue-approved"]), 2)

if __name__ == "__main__":
    unittest.main()
