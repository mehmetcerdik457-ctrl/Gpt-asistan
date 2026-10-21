"""No-network security tests for the limited one-time GitHub branch pilot."""
import os
import unittest
from unittest.mock import patch

from server import github_push_pilot as pilot
from server import github_issue_bridge as bridge


def issue():
    return {
        "number": 40,
        "state": "open",
        "title": "[KRAL-CHECK] KRAL/CİHAT ilk görev",
        "body": "Kaynak CI testlerini çalıştır.",
        "user": {"login": bridge.OWNER_LOGIN},
    }


def env():
    return {
        "GITHUB_REPOSITORY": bridge.REPOSITORY,
        "GITHUB_ACTOR": bridge.OWNER_LOGIN,
        "GITHUB_REF": pilot.PILOT_BRANCH,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "1234567",
        "GITHUB_TOKEN": "dummy",
    }


class BranchPilotTests(unittest.TestCase):
    def test_strict_environment_gate(self):
        self.assertTrue(pilot.approved_environment(env()))
        for key, value in (
            ("GITHUB_REPOSITORY", "other/repo"),
            ("GITHUB_ACTOR", "another-user"),
            ("GITHUB_REF", "refs/heads/main"),
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_SHA", "bad"),
            ("GITHUB_RUN_ID", "not-a-number"),
        ):
            with self.subTest(key=key):
                bad = env()
                bad[key] = value
                self.assertFalse(pilot.approved_environment(bad))

    def test_fails_closed_without_owner_issue(self):
        for key, value in (
            ("user", {"login": "attacker"}),
            ("title", "Not an authorized check"),
            ("state", "closed"),
            ("number", 41),
            ("pull_request", {"url": "not-an-issue"}),
        ):
            with self.subTest(key=key):
                target = issue()
                target[key] = value
                with patch.dict(os.environ, env(), clear=True), patch.object(pilot, "read_current_issue", return_value=target):
                    with self.assertRaises(bridge.TaskRejected):
                        pilot.run()

    def test_posts_exact_fixed_comment_when_verified(self):
        with patch.dict(os.environ, env(), clear=True), \
             patch.object(pilot, "read_current_issue", return_value=issue()), \
             patch.object(bridge, "already_answered", return_value=False) as already, \
             patch.object(bridge, "make_check_comment", return_value="verified CI") as make_comment, \
             patch.object(bridge, "github_json", return_value={}) as send:
            pilot.run()
            already.assert_called_once_with(40, "dummy", bridge.CHECK_MARKER)
            self.assertEqual(make_comment.call_args.args[1:], ("1234567", "a" * 40))
            send.assert_called_once_with("POST", "/issues/40/comments", "dummy", {"body": "verified CI"})

    def test_idempotent_does_not_post_again(self):
        with patch.dict(os.environ, env(), clear=True), \
             patch.object(pilot, "read_current_issue", return_value=issue()), \
             patch.object(bridge, "already_answered", return_value=True), \
             patch.object(bridge, "make_check_comment") as build, \
             patch.object(bridge, "github_json") as post:
            pilot.run()
            build.assert_not_called()
            post.assert_not_called()

    def test_unconfigured_token_rejected(self):
        with self.assertRaises(bridge.TaskRejected):
            pilot.read_current_issue("")


if __name__ == "__main__":
    unittest.main()
