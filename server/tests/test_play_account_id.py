import unittest
from server.play_account_id import obfuscated_play_account_id


class AccountIdTests(unittest.TestCase):
    def setUp(self): self.secret = b"offline-only-test-secret-32-bytes-minimum"
    def derive(self, owner="owner-1", secret=None):
        return obfuscated_play_account_id(authenticated_owner_id=owner,
                                          server_secret=self.secret if secret is None else secret)
    def test_stable(self): self.assertEqual(self.derive(), self.derive())
    def test_distinct_users(self): self.assertNotEqual(self.derive("owner-1"), self.derive("owner-2"))
    def test_distinct_secrets(self): self.assertNotEqual(self.derive(), self.derive(secret=b"other-offline-test-secret-32-bytes-minimum"))
    def test_not_plaintext(self): self.assertNotIn("owner-1", self.derive())
    def test_length(self): self.assertEqual(len(self.derive()), 64)
    def test_short_secret_rejected(self):
        with self.assertRaises(ValueError): self.derive(secret=b"short")
    def test_empty_owner_rejected(self):
        with self.assertRaises(ValueError): self.derive(owner="")
    def test_oversized_owner_rejected(self):
        with self.assertRaises(ValueError): self.derive(owner="a"*257)


if __name__ == "__main__": unittest.main()
