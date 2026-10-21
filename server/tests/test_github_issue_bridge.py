"""Offline tests: no GitHub, model provider, or device connection."""
import unittest
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

    def test_idempotent_comments(self):
        with patch.object(b, "github_json", return_value=[{"body": "hello " + b.MARKER}]):
            self.assertTrue(b.already_answered(7, "token"))
        with patch.object(b, "github_json", return_value=[{"body": "other"}]):
            self.assertFalse(b.already_answered(7, "token"))
        with patch.object(b, "github_json", return_value=[{}] * 100):
            with self.assertRaises(b.TaskRejected):
                b.already_answered(7, "token")

    def test_no_github_access_without_token(self):
        with self.assertRaises(b.TaskRejected):
            b.github_json("GET", "/issues/7/comments", "")
        with self.assertRaises(b.TaskRejected):
            b.github_json("POST", "/repos/other", "token")


if __name__ == "__main__":
    unittest.main()
