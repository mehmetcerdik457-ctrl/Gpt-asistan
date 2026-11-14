"""Offline ADC credential tests: no real Google account or Play API calls."""
from datetime import datetime, timezone
import unittest
from server.play_google_oauth import (
    PlayPublisherOAuth, PublisherOAuthUnavailable, ANDROIDPUBLISHER_SCOPE)

EMAIL = "orba-developer@play-test.iam.gserviceaccount.com"
NOW = 1794000000

class FakeCredentials:
    def __init__(self, email=EMAIL, token="synthetic-access-token", ttl=3600,
                 scopes=True, refresh_error=None):
        self.service_account_email = email
        self.token = token
        self.expiry = datetime.fromtimestamp(NOW + ttl, tz=timezone.utc)
        self.has_permissions = scopes
        self.refresh_error = refresh_error
        self.refreshed = 0
    def has_scopes(self, scopes):
        assert scopes == [ANDROIDPUBLISHER_SCOPE]
        return self.has_permissions
    def refresh(self, request):
        self.refreshed += 1
        if self.refresh_error:
            raise RuntimeError(self.refresh_error)
        self.token = "new-synthetic-access-token"
        self.expiry = datetime.fromtimestamp(NOW + 3600, tz=timezone.utc)

class Tests(unittest.TestCase):
    def make(self, creds=None, enabled=True, loader_calls=None, **kwargs):
        c = creds or FakeCredentials()
        calls = loader_calls if loader_calls is not None else []
        def loader(*, scopes):
            calls.append(list(scopes))
            return c, "synthetic-project"
        return PlayPublisherOAuth(
            service_account_email=EMAIL,
            credential_loader=loader,
            request_factory=lambda: "synthetic-request",
            now=lambda: NOW,
            enabled=lambda: enabled,
            **kwargs)

    def test_disabled_before_any_credentials_loaded(self):
        calls=[]
        with self.assertRaisesRegex(PublisherOAuthUnavailable,"PUBLISHER_OAUTH_DISABLED"):
            self.make(enabled=False, loader_calls=calls)()
        self.assertEqual(calls,[])

    def test_expected_service_account_returns_bounded_token(self):
        calls=[]
        p = self.make(loader_calls=calls)
        self.assertEqual(p(),"synthetic-access-token")
        self.assertEqual(calls, [[ANDROIDPUBLISHER_SCOPE]])

    def test_cache_does_not_reload_credentials(self):
        calls=[]
        p=self.make(loader_calls=calls)
        self.assertEqual(p(),p())
        self.assertEqual(len(calls),1)

    def test_refresh_near_expiry(self):
        c=FakeCredentials(ttl=30)
        self.assertEqual(self.make(creds=c)(),"new-synthetic-access-token")
        self.assertEqual(c.refreshed,1)

    def test_refresh_expired(self):
        c=FakeCredentials(ttl=-1)
        self.assertEqual(self.make(creds=c)(),"new-synthetic-access-token")
        self.assertEqual(c.refreshed,1)

    def test_no_refresh_when_sufficient_ttl(self):
        c=FakeCredentials(ttl=61)
        self.make(creds=c)()
        self.assertEqual(c.refreshed,0)

    def test_exact_60_second_margin_refresh(self):
        c=FakeCredentials(ttl=60)
        self.make(creds=c)()
        self.assertEqual(c.refreshed,1)

    def test_wrong_service_account_denied(self):
        c=FakeCredentials(email="other@play-test.iam.gserviceaccount.com")
        with self.assertRaisesRegex(PublisherOAuthUnavailable,"UNAVAILABLE"):
            self.make(creds=c)()

    def test_user_credentials_without_service_account_denied(self):
        c=FakeCredentials()
        c.service_account_email=None
        with self.assertRaises(PublisherOAuthUnavailable):
            self.make(creds=c)()

    def test_lacking_androidpublisher_scope_denied(self):
        with self.assertRaises(PublisherOAuthUnavailable):
            self.make(creds=FakeCredentials(scopes=False))()

    def test_refresh_failure_redacts_secret_and_identity(self):
        c=FakeCredentials(ttl=-1,refresh_error="SECRET_DO_NOT_LOG")
        with self.assertRaises(PublisherOAuthUnavailable) as err:
            self.make(creds=c)()
        self.assertNotIn("SECRET_DO_NOT_LOG",str(err.exception))
        self.assertNotIn(EMAIL,str(err.exception))

    def test_newline_token_rejected(self):
        c=FakeCredentials(token="bad\ninjected",ttl=3600)
        self.assertEqual(self.make(creds=c)(),"new-synthetic-access-token")
        self.assertEqual(c.refreshed,1)

    def test_whitespace_token_rejected(self):
        c=FakeCredentials(token="bad token",ttl=3600)
        self.assertEqual(self.make(creds=c)(),"new-synthetic-access-token")

    def test_invalid_refreshed_token_denied(self):
        c=FakeCredentials(ttl=-1)
        def no_valid_refresh(_req):
            c.token="bad\nvalue"
            c.expiry=datetime.fromtimestamp(NOW+3600,tz=timezone.utc)
        c.refresh=no_valid_refresh
        with self.assertRaises(PublisherOAuthUnavailable):
            self.make(creds=c)()

    def test_invalid_service_account_email_rejected(self):
        with self.assertRaises(ValueError):
            PlayPublisherOAuth(service_account_email="user@example.com")

    def test_does_not_enable_any_http_routes(self):
        p=self.make()
        self.assertIsInstance(p,PlayPublisherOAuth)
        self.assertFalse(hasattr(p,"deploy"))
        self.assertFalse(hasattr(p,"create_subscription"))

    def test_missing_expiry_refreshes_and_denies_if_still_missing(self):
        c=FakeCredentials()
        c.expiry=None
        def fail_expiry(_request):
            c.token="synthetic"
            c.expiry=None
        c.refresh=fail_expiry
        with self.assertRaises(PublisherOAuthUnavailable):
            self.make(creds=c)()


if __name__=="__main__": unittest.main()
