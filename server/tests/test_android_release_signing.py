"""Synthetic release fixtures; no production signing identity is generated."""
import subprocess
import unittest
from unittest.mock import Mock

from server.tests import test_android_owner_signing as owner_signing_tests


class ReleaseSigningTests(unittest.TestCase):
    fake_tool = owner_signing_tests.OwnerSigningTests.fake_tool

    def setUp(self):
        owner_signing_tests.OwnerSigningTests.setUp(self)
        self.config["release_branch"] = "main"
        self.env["GITHUB_REF"] = "refs/heads/main"
        self.bundle = self.workspace / "release.aab"
        self.bundle.write_bytes(b"original AAB fixture")

    def fake_release_tool(self, args, **kwargs):
        if args[0] == "jarsigner":
            if "-signedjar" in args:
                self.assertNotIn("STORE_PASSWORD_SENTINEL", args)
                self.assertNotIn("KEY_PASSWORD_SENTINEL", args)
                self.assertIn("-storepass:env", args)
                self.assertIn("-keypass:env", args)
                self.assertIn("SHA-256", args)
                self.assertNotIn("-sigalg", args)  # support existing RSA or EC keys
                target = args[args.index("-signedjar") + 1]
                from pathlib import Path
                Path(target).write_bytes(b"signed AAB fixture")
            else:
                self.assertIn("-strict", args)
                self.assertIn("-keystore", args)
                self.assertEqual(args[-1], "alias-fixture")
            return subprocess.CompletedProcess(args, 0, stdout=b"")
        return self.fake_tool(args, **kwargs)

    def test_signs_apk_and_bundle_with_same_pinned_identity(self):
        result = self.m.sign_release(self.apks[0], self.bundle, self.config, self.env,
                                     "apksigner", runner=self.fake_release_tool)
        self.assertTrue(result["owner_signing_verified"])
        self.assertTrue(result["release_apk_aab_verified"])
        self.assertFalse(result["new_key_created"])
        self.assertEqual(self.apks[0].read_bytes(), b"signed APK fixture")
        self.assertEqual(self.bundle.read_bytes(), b"signed AAB fixture")
        self.assertEqual(list(self.runner_temp.iterdir()), [])

    def test_bundle_verification_failure_preserves_both_originals(self):
        def reject_bundle(args, **kwargs):
            if args[0] == "jarsigner" and "-verify" in args:
                raise subprocess.CalledProcessError(16, args, stderr=b"KEY_PASSWORD_SENTINEL")
            return self.fake_release_tool(args, **kwargs)
        with self.assertRaisesRegex(self.m.SigningRejected, "^OWNER_SIGNING_TOOL_FAILED$"):
            self.m.sign_release(self.apks[0], self.bundle, self.config, self.env,
                                "apksigner", runner=reject_bundle)
        self.assertEqual(self.apks[0].read_bytes(), b"original APK fixture")
        self.assertEqual(self.bundle.read_bytes(), b"original AAB fixture")
        self.assertEqual(list(self.runner_temp.iterdir()), [])

    def test_untrusted_release_never_reads_any_secret(self):
        class GuardedEnv(dict):
            def get(inner, key, default=None):
                if key in self.m.SECRET_NAMES:
                    raise AssertionError("untrusted event read a credential")
                return super().get(key, default)
        for field, value in (("GITHUB_REF", "refs/heads/untrusted"),
                             ("GITHUB_ACTOR", "untrusted"),
                             ("GITHUB_REPOSITORY", "untrusted/repo"),
                             ("GITHUB_EVENT_NAME", "pull_request")):
            with self.subTest(field=field):
                runner = Mock()
                result = self.m.sign_release(self.apks[0], self.bundle, self.config,
                                             GuardedEnv(self.env, **{field: value}),
                                             "apksigner", runner=runner)
                self.assertEqual(result["status"], "BLOCKED_RELEASE_UNTRUSTED_EVENT")
                runner.assert_not_called()

    def test_missing_release_secrets_never_publish_success(self):
        env = {key: value for key, value in self.env.items() if key not in self.m.SECRET_NAMES}
        runner = Mock()
        result = self.m.sign_release(self.apks[0], self.bundle, self.config, env,
                                    "apksigner", runner=runner)
        self.assertEqual(result["status"], "BLOCKED_OWNER_SECRETS_MISSING")
        self.assertFalse(result["release_apk_aab_verified"])
        runner.assert_not_called()

    def test_release_rejects_symlink_inputs(self):
        link = self.workspace / "linked.aab"
        link.symlink_to(self.bundle)
        with self.assertRaisesRegex(self.m.SigningRejected, "RELEASE_INPUT_INVALID"):
            self.m.sign_release(self.apks[0], link, self.config, self.env, "apksigner")

