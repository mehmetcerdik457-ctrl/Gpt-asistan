"""Synthetic keystore/tool fixtures only; these are not owner signing evidence."""
import base64
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from server.tests.test_android_delivery_evidence import module


class OwnerSigningTests(unittest.TestCase):
    def setUp(self):
        self.m = module("android_owner_signing")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.runner_temp = self.root / "runner-temp"
        self.runner_temp.mkdir()
        self.apks = [self.workspace / "app.apk", self.workspace / "test.apk"]
        for path in self.apks:
            path.write_bytes(b"original APK fixture")
        self.cert = b"public certificate fixture, no private key"
        self.digest = hashlib.sha256(self.cert).hexdigest()
        self.config = {"repository": "owner/repo", "trusted_branch": "approved", "actor": "owner",
                       "certificate_sha256": self.digest}
        self.env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": "owner/repo",
                    "GITHUB_REF": "refs/heads/approved", "GITHUB_ACTOR": "owner",
                    "GITHUB_WORKSPACE": str(self.workspace), "RUNNER_TEMP": str(self.runner_temp),
                    "ANDROID_KEYSTORE_BASE64": base64.b64encode(b"not a real keystore").decode(),
                    "ANDROID_KEY_ALIAS": "alias-fixture", "ANDROID_KEY_PASSWORD": "KEY_PASSWORD_SENTINEL",
                    "ANDROID_STORE_PASSWORD": "STORE_PASSWORD_SENTINEL"}

    def fake_tool(self, args, **kwargs):
        if args[0] == "keytool":
            key = Path(args[args.index("-keystore") + 1])
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(str(self.workspace), str(key))
            return subprocess.CompletedProcess(args, 0, stdout=self.cert)
        if args[1] == "sign":
            Path(args[args.index("--out") + 1]).write_bytes(b"signed APK fixture")
            self.assertIn("env:ANDROID_STORE_PASSWORD", args)
            self.assertNotIn("STORE_PASSWORD_SENTINEL", args)
            return subprocess.CompletedProcess(args, 0, stdout=b"")
        return subprocess.CompletedProcess(args, 0, stdout=(
            "Signer #1 certificate SHA-256 digest: " + self.digest + "\n").encode())

    def test_pinned_signer_stages_both_apks_and_cleans_temporary_keystore(self):
        result = self.m.sign_existing(self.apks, self.config, self.env, "apksigner", runner=self.fake_tool)
        self.assertTrue(result["owner_signing_verified"])
        self.assertFalse(result["new_key_created"])
        self.assertFalse(result["previous_install_upgrade_verified"])
        self.assertEqual([p.read_bytes() for p in self.apks], [b"signed APK fixture"] * 2)
        self.assertEqual(list(self.runner_temp.iterdir()), [])

    def test_pr_never_reads_signing_secret_fields(self):
        class GuardedEnv(dict):
            def get(inner, key, default=None):
                if key in self.m.SECRET_NAMES:
                    raise AssertionError("PR read a signing credential")
                return super().get(key, default)
        env = GuardedEnv(self.env, GITHUB_EVENT_NAME="pull_request")
        runner = Mock()
        result = self.m.sign_existing(self.apks, self.config, env, "apksigner", runner=runner)
        self.assertEqual(result["status"], "DEBUG_ONLY_UNTRUSTED_EVENT")
        runner.assert_not_called()

    def test_missing_secrets_are_reported_without_generating_a_key(self):
        env = {k: v for k, v in self.env.items() if k not in self.m.SECRET_NAMES}
        runner = Mock()
        result = self.m.sign_existing(self.apks, self.config, env, "apksigner", runner=runner)
        self.assertEqual(result["status"], "BLOCKED_OWNER_SECRETS_MISSING")
        self.assertEqual(result["missing_secret_names"], list(self.m.SECRET_NAMES))
        runner.assert_not_called()

    def test_invalid_encoding_never_reaches_a_signing_tool(self):
        env = dict(self.env, ANDROID_KEYSTORE_BASE64="!invalid!")
        runner = Mock()
        with self.assertRaisesRegex(self.m.SigningRejected, "ENCODING_INVALID"):
            self.m.sign_existing(self.apks, self.config, env, "apksigner", runner=runner)
        runner.assert_not_called()

    def test_wrong_keystore_certificate_does_not_replace_any_apk(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=b"another public certificate"))
        with self.assertRaisesRegex(self.m.SigningRejected, "CERT_PIN_MISMATCH"):
            self.m.sign_existing(self.apks, self.config, self.env, "apksigner", runner=runner)
        self.assertEqual([p.read_bytes() for p in self.apks], [b"original APK fixture"] * 2)
        self.assertEqual(list(self.runner_temp.iterdir()), [])

    def test_tool_errors_do_not_expose_stderr_or_passwords(self):
        runner = Mock(side_effect=subprocess.CalledProcessError(1, ["tool"], stderr=b"STORE_PASSWORD_SENTINEL"))
        with self.assertRaises(self.m.SigningRejected) as context:
            self.m.sign_existing(self.apks, self.config, self.env, "apksigner", runner=runner)
        self.assertEqual(str(context.exception), "OWNER_SIGNING_TOOL_FAILED")
        self.assertNotIn("PASSWORD_SENTINEL", str(context.exception))

    def test_second_apk_failure_keeps_both_original_outputs(self):
        verifies = 0
        def fail_second(args, **kwargs):
            nonlocal verifies
            if len(args) > 1 and args[1] == "verify":
                verifies += 1
                if verifies == 2:
                    return subprocess.CompletedProcess(args, 0, stdout=(
                        "Signer #1 certificate SHA-256 digest: " + "0" * 64 + "\n").encode())
            return self.fake_tool(args, **kwargs)
        with self.assertRaisesRegex(self.m.SigningRejected, "SIGNED_APK_CERT_MISMATCH"):
            self.m.sign_existing(self.apks, self.config, self.env, "apksigner", runner=fail_second)
        self.assertEqual([p.read_bytes() for p in self.apks], [b"original APK fixture"] * 2)
        self.assertEqual(list(self.runner_temp.iterdir()), [])

    def test_wrong_actor_ref_or_repo_cannot_use_a_keystore(self):
        for key in ("GITHUB_ACTOR", "GITHUB_REF", "GITHUB_REPOSITORY"):
            with self.subTest(field=key):
                runner = Mock()
                result = self.m.sign_existing(self.apks, self.config, dict(self.env, **{key: "untrusted"}),
                                              "apksigner", runner=runner)
                self.assertFalse(result["owner_signing_verified"])
                runner.assert_not_called()

    def test_keystore_must_not_be_written_under_uploaded_workspace(self):
        env = dict(self.env, RUNNER_TEMP=str(self.workspace / "unsafe-temp"))
        with self.assertRaisesRegex(self.m.SigningRejected, "OUTSIDE_WORKSPACE"):
            self.m.sign_existing(self.apks, self.config, env, "apksigner")

    def test_ambiguous_or_wrong_signer_output_is_rejected(self):
        value = "Signer #1 certificate SHA-256 digest: " + self.digest + "\n"
        self.assertEqual(self.m.signer_digest(value), self.digest)
        for output in ("", value + value, value.replace("#1", "#2")):
            with self.assertRaises(self.m.SigningRejected):
                self.m.signer_digest(output)
