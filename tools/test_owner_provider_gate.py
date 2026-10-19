"""Source-level owner/Keystore gate regression checks; not Android device tests."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "app/src/main/java/com/mehmetcerdik/ownerai"

class OwnerProviderGateTests(unittest.TestCase):
    def test_provider_request_always_requires_fresh_owner(self):
        activity = (PKG / "OwnerBrainActivity.java").read_text()
        gate = activity.split("private void requireForRequest(", 1)[1].split("private void runBrain(", 1)[0]
        self.assertIn("OwnerAuth.requireFresh(this, action,", gate)
        self.assertNotIn("OwnerAuth.require(this, action,", gate)

    def test_ocr_provider_request_requires_fresh_owner(self):
        activity = (PKG / "OwnerBrainActivity.java").read_text()
        self.assertIn("ocr.setOnClickListener(v -> OwnerAuth.requireFresh(this, () -> {", activity)

    def test_keystore_authentication_remains_required(self):
        secret = (PKG / "SecureSecrets.java").read_text()
        self.assertIn(".setUserAuthenticationRequired(true)", secret)
        self.assertIn("AUTH_VALIDITY_SECONDS = 30", secret)
        self.assertIn("PROVIDER_SECRET_USE_REQUIRES_RECENT_OWNER_AUTH", secret)

    def test_provider_endpoint_still_enforces_tls_and_host(self):
        policy = (PKG / "ProviderEndpointPolicy.java").read_text()
        self.assertIn('!"https".equalsIgnoreCase(uri.getScheme())', policy)
        self.assertIn('!"api.openai.com".equals(host.toLowerCase(Locale.ROOT))', policy)
        self.assertIn('"PROVIDER_ENDPOINT_DENIED"', policy)

    def test_network_errors_are_safe_and_distinct(self):
        engine = (PKG / "OwnerBrainEngine.java").read_text()
        self.assertIn("catch (java.io.IOException e)", engine)
        self.assertIn("ProviderNetworkErrors.code(e)", engine)
        self.assertIn("fail(safeCode)", engine)
        self.assertIn("c.setInstanceFollowRedirects(false)", engine)
        self.assertIn("PROVIDER_REDIRECT_DENIED", engine)

if __name__ == "__main__":
    unittest.main()
