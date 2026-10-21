"""Offline tests: no GitHub, model provider, or device connection."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import github_issue_bridge as b


class FakeProvider:
    def __init__(self, configured=True, candidates=("allowed-model",)):
        self.is_configured = configured
        self.models = candidates
        self.received = []

    def configured(self):
        return self.is_configured

    def candidates(self):
        return self.models

    def reply(self, model, message):
        self.received.append((model, message))
        return "Önce testleri kontrol et.", "allowed-model", 25


def event():
    return {
        "action": "labeled", "repository": {"full_name": b.REPOSITORY},
        "label": {"name": b.LABEL},
        "issue": {"number": 7, "state": "open", "title": "Test görevi", "body": "Salt-okunur incele.",
                  "user": {"login": b.OWNER_LOGIN}, "labels": [{"name": b.LABEL}]},
    }


class BridgeTests(unittest.TestCase):
    def test_accepted_task(self):
        self.assertEqual(b.validate_event(event()), (7, "Test görevi\n\nSalt-okunur incele."))

    def test_reject_misrouted_and_unapproved_events(self):
        mutations = [
            lambda e: e.update(action="opened"),
            lambda e: e["repository"].update(full_name="someone/other"),
            lambda e: e["label"].update(name="bug"),
            lambda e: e["issue"]["user"].update(login="outsider"),
            lambda e: e["issue"].update(state="closed"),
            lambda e: e["issue"].update(pull_request={"url": "fake"}),
            lambda e: e["issue"].update(labels=[]),
            lambda e: e["issue"].update(number=True),
            lambda e: e["issue"].update(body="x" * 5000),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = event()
                mutate(data)
                with self.assertRaises(b.TaskRejected):
                    b.validate_event(data)

    def test_advisory_cannot_claim_execution(self):
        provider = FakeProvider()
        reply = b.make_advisory("Görevi kontrol et", provider)
        self.assertIn("yürütme: KAPALI", reply)
        self.assertIn(b.MARKER, reply)
        self.assertEqual(provider.received[0][0], "allowed-model")
        self.assertIn("Do not claim to have run code", provider.received[0][1])

    def test_missing_provider_is_fail_closed(self):
        for provider in (FakeProvider(configured=False), FakeProvider(candidates=())):
            with self.assertRaises(b.TaskRejected):
                b.make_advisory("Görev", provider)
            self.assertEqual(provider.received, [])

    def test_check_task_accepts_owner_open_and_edit_only(self):
        data = event()
        data["action"] = "opened"
        data["issue"]["title"] = "[KRAL-CHECK] Kodu doğrula"
        self.assertEqual(b.validate_check_event(data)[0], 7)
        data["action"] = "edited"
        self.assertEqual(b.validate_check_event(data)[0], 7)

    def test_check_rejects_unsafe_or_misrouted_events(self):
        mutations = [
            lambda e: e.update(action="labeled"),
            lambda e: e["repository"].update(full_name="other/repo"),
            lambda e: e["issue"]["user"].update(login="other"),
            lambda e: e["issue"].update(title="[KRAL-CHECK]"),
            lambda e: e["issue"].update(state="closed"),
            lambda e: e["issue"].update(pull_request={"url": "fake"}),
            lambda e: e["issue"].update(body="x" * 5000),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                data = event()
                data["action"] = "opened"
                data["issue"]["title"] = "[KRAL-CHECK] Kodu doğrula"
                mutate(data)
                with self.assertRaises(b.TaskRejected):
                    b.validate_check_event(data)

    def test_check_report_only_from_genuine_pass_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kral-checks.log"
            path.write_text("test_a ... ok\n\nRan 7 tests in 0.123s\n\nOK\n", encoding="utf-8")
            comment = b.make_check_comment(path, "39646053958", "e" * 40)
            self.assertIn("7 PASS", comment)
            self.assertIn(b.CHECK_MARKER, comment)
            self.assertIn("DOĞRULANMADI", comment)
            for invalid_log in ("Ran 0 tests in 0.1s\n\nOK", "Ran 4 tests in 1.0s\n\nFAILED (failures=1)"):
                path.write_text(invalid_log, encoding="utf-8")
                with self.assertRaises(b.TaskRejected):
                    b.make_check_comment(path, "39646053958", "e" * 40)
            path.write_text("Ran 4 tests in 1.0s\n\nOK", encoding="utf-8")
            with self.assertRaises(b.TaskRejected):
                b.make_check_comment(path, "not-run-id", "e" * 40)
            with self.assertRaises(b.TaskRejected):
                b.make_check_comment(path, "39646053958", "not-a-sha")

    def test_idempotent_comments_ignore_forged_user(self):
        fake = [{"body": b.ADVICE_MARKER, "user": {"login": "attacker"}}]
        with patch.object(b, "github_json", return_value=fake):
            self.assertFalse(b.already_answered(7, "token"))
        real = [{"body": "hello " + b.ADVICE_MARKER, "user": {"login": "github-actions[bot]"}}]
        with patch.object(b, "github_json", return_value=real):
            self.assertTrue(b.already_answered(7, "token"))
            self.assertFalse(b.already_answered(7, "token", b.CHECK_MARKER))
        with patch.object(b, "github_json", return_value=[{}] * 100):
            with self.assertRaises(b.TaskRejected):
                b.already_answered(7, "token")

    def test_no_github_access_without_token_or_fixed_path(self):
        invalid = [
            ("GET", "/issues/7/comments", ""),
            ("POST", "/repos/other", "token"),
            ("DELETE", "/issues/7/comments", "token"),
            ("GET", "/issues/7/../../secrets", "token"),
        ]
        for method, path, token in invalid:
            with self.assertRaises(b.TaskRejected):
                b.github_json(method, path, token)

    def test_redirect_is_never_followed_with_auth_header(self):
        with self.assertRaises(b.TaskRejected):
            b.NoRedirect().redirect_request(None, None, 302, "Moved", {}, "https://other.example")


if __name__ == "__main__":
    unittest.main()
