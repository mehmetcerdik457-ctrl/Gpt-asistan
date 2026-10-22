"""Offline tests: any owner issue can request fixed CI, no arbitrary task execution."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import github_push_pilot as queue
from server import github_issue_bridge as bridge


def issue(number=41):
    return {
        "number": number, "state": "open",
        "title": "[KRAL-CHECK] Sabit kaynak testini doğrula",
        "body": "Hesap ve kaynak bilgilerini değiştirme. rm -rf / bir test komutu değildir.",
        "user": {"login": bridge.OWNER_LOGIN},
    }


def env():
    return {
        "GITHUB_REPOSITORY": bridge.REPOSITORY,
        "GITHUB_ACTOR": bridge.OWNER_LOGIN,
        "GITHUB_REF": queue.PILOT_BRANCH,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "1234567",
        "GITHUB_TOKEN": "dummy",
    }


def ticket(n=41):
    return {"schema": 1, "repository": bridge.REPOSITORY, "operation": "fixed_ci", "issue_number": n}


class ReusableBranchTaskTests(unittest.TestCase):
    def test_environment_gate_rejects_misroute(self):
        self.assertTrue(queue.approved_environment(env()))
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
                self.assertFalse(queue.approved_environment(bad))

    def test_ticket_only_allows_known_fixed_ci_operation(self):
        self.assertEqual(queue.parse_ticket(ticket()), 41)
        self.assertEqual(queue.parse_ticket(ticket(40)), 40)
        mutations = [
            {"schema": True},
            {"schema": 2},
            {"repository": "someone/other"},
            {"operation": "execute_shell"},
            {"operation": "call_model"},
            {"issue_number": -1},
            {"issue_number": True},
            {"issue_number": "41"},
            {"issue_number": 0},
            {"issue_number": 100000001},
            {"secret": "injection"},
        ]
        for update in mutations:
            with self.subTest(update=update):
                value = {**ticket(), **update}
                with self.assertRaises(bridge.TaskRejected):
                    queue.parse_ticket(value)
        for obj in ([], "", 41, {"issue_number": 41}):
            with self.assertRaises(bridge.TaskRejected):
                queue.parse_ticket(obj)

    def test_ticket_file_checks_bounds_and_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ticket.json"
            path.write_text(json.dumps(ticket()), encoding="utf-8")
            self.assertEqual(queue.load_ticket(path), 41)
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(bridge.TaskRejected):
                queue.load_ticket(path)
            path.write_text(" " * 2050, encoding="utf-8")
            with self.assertRaises(bridge.TaskRejected):
                queue.load_ticket(path)
            path.unlink()
            path.symlink_to(Path(folder) / "missing")
            with self.assertRaises(bridge.TaskRejected):
                queue.load_ticket(path)

    def test_live_issue_author_and_prefix_verified_every_run(self):
        for attr, value in (
            ("user", {"login": "attacker"}),
            ("title", "Run arbitrary code"),
            ("state", "closed"),
            ("number", 40),
            ("pull_request", {"url": "not-issue"}),
        ):
            with self.subTest(attr=attr):
                item = issue()
                item[attr] = value
                with patch.dict(os.environ, env(), clear=True), \
                     patch.object(queue, "load_ticket", return_value=41), \
                     patch.object(queue, "read_current_issue", return_value=item):
                    with self.assertRaises(bridge.TaskRejected):
                        queue.run()

    def test_posts_proven_fixed_result_to_selected_owner_issue(self):
        for number in (41, 42):
            with self.subTest(number=number), \
                 patch.dict(os.environ, env(), clear=True), \
                 patch.object(queue, "load_ticket", return_value=number), \
                 patch.object(queue, "read_current_issue", return_value=issue(number)) as read, \
                 patch.object(bridge, "already_answered", return_value=False) as seen, \
                 patch.object(bridge, "make_check_comment", return_value="verified evidence") as build, \
                 patch.object(bridge, "github_json", return_value={}) as post:
                queue.run()
                read.assert_called_once_with("dummy", number)
                seen.assert_called_once_with(number, "dummy", bridge.CHECK_MARKER)
                self.assertEqual(build.call_args.args[1:], ("1234567", "a" * 40))
                post.assert_called_once_with("POST", f"/issues/{number}/comments", "dummy", {"body": "verified evidence"})

    def test_bot_comment_idempotency(self):
        with patch.dict(os.environ, env(), clear=True), \
             patch.object(queue, "load_ticket", return_value=41), \
             patch.object(queue, "read_current_issue", return_value=issue()), \
             patch.object(bridge, "already_answered", return_value=True), \
             patch.object(bridge, "make_check_comment") as build, \
             patch.object(bridge, "github_json") as post:
            queue.run()
            build.assert_not_called()
            post.assert_not_called()

    def test_network_rejects_bad_token_issue_number_and_redirect(self):
        with self.assertRaises(bridge.TaskRejected):
            queue.read_current_issue("", 41)
        for item in (True, 0, -1, "41", 100000001):
            with self.subTest(value=item):
                with self.assertRaises(bridge.TaskRejected):
                    queue.read_current_issue("dummy", item)
        with self.assertRaises(bridge.TaskRejected):
            bridge.NoRedirect().redirect_request(None, None, 302, "Moved", {}, "https://evil.example")

    def test_issue_body_never_converted_to_commands_or_prompts(self):
        with patch.dict(os.environ, env(), clear=True), \
             patch.object(queue, "load_ticket", return_value=41), \
             patch.object(queue, "read_current_issue", return_value=issue()), \
             patch.object(bridge, "already_answered", return_value=False), \
             patch.object(bridge, "make_check_comment", return_value="passed fixed CI"), \
             patch.object(bridge, "github_json") as post:
            queue.run()
            text = post.call_args.args[3]["body"]
            self.assertEqual(text, "passed fixed CI")
            self.assertNotIn("rm -rf", text)


if __name__ == "__main__":
    unittest.main()
