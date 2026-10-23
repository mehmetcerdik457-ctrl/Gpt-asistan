"""Read-only source endpoint tests without production identity or provider."""
import hashlib
import http.client
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from server.source_owner_tool import inspect_source, SourceInspectionDenied
from server.gateway import Gateway, handler_for, BoundedThreadingHTTPServer, Denied


class DisabledProvider:
    name = "none"
    def configured(self):
        return False


class InspectSourceTests(unittest.TestCase):
    def test_inspect_explicit_apk_one_file_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "app.apk"
            with ZipFile(p, "w") as z:
                z.writestr("AndroidManifest.xml", b"static")
                z.writestr("classes.dex", b"static")
            before = (p.stat().st_mtime_ns, p.read_bytes())
            got = inspect_source(tmp, "app.apk")
            self.assertEqual(got["status"], "ANALYZED_STATIC")
            self.assertEqual(got["apk_structure"]["dex_count"], 1)
            self.assertEqual(got["sha256"], hashlib.sha256(before[1]).hexdigest())
            self.assertEqual(before, (p.stat().st_mtime_ns, p.read_bytes()))
            self.assertEqual(got["integration_status"], "NOT_CONNECTED")

    def test_disabled_by_default(self):
        with self.assertRaises(SourceInspectionDenied) as err:
            inspect_source("", "any.apk")
        self.assertEqual(str(err.exception), "SOURCE_ROOT_NOT_CONFIGURED")

    def test_arbitrary_absolute_path_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SourceInspectionDenied):
                inspect_source(tmp, "/etc/passwd")

    def test_traversal_and_hidden_sources_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in ("../secret.json", "dir/../secret.json",
                          ".env", ".git/config.json", "a//b.apk", "./x.apk",
                          "secrets/key.json", "dir\\file.apk"):
                with self.subTest(value=value):
                    with self.assertRaises(SourceInspectionDenied):
                        inspect_source(tmp, value)

    def test_regular_allowed_document_hash_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "source.py"
            p.write_text("print('NEVER RUN THIS')", encoding="utf-8")
            got = inspect_source(tmp, "source.py")
            self.assertEqual(got["status"], "VERIFIED_FILE")
            self.assertEqual(got["capability_status"], "UNTESTED")

    def test_nested_directory_allowed_and_symlink_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "source"
            folder.mkdir()
            (folder / "app.apk").write_bytes(b"invalid ZIP")
            got = inspect_source(tmp, "source/app.apk")
            self.assertEqual(got["apk_structure"]["status"], "BLOCKED")
            alias = Path(tmp) / "alias"
            alias.symlink_to(folder, target_is_directory=True)
            with self.assertRaises(SourceInspectionDenied) as err:
                inspect_source(tmp, "alias/app.apk")
            self.assertEqual(str(err.exception), "SOURCE_LINK_DENIED")

    def test_oversize_source_denied_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "large.zip"
            p.write_bytes(b"x"*12)
            with self.assertRaises(SourceInspectionDenied) as err:
                inspect_source(tmp, "large.zip", max_file_bytes=4)
            self.assertEqual(str(err.exception), "SOURCE_SIZE_LIMIT")

    def test_unknown_extension_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "file.bin").write_bytes(b"test")
            with self.assertRaises(SourceInspectionDenied) as err:
                inspect_source(tmp, "file.bin")
            self.assertEqual(str(err.exception), "SOURCE_TYPE_NOT_ALLOWED")

    def test_gateway_owner_route_disabled_without_mount(self):
        gateway = Gateway(object(), provider=DisabledProvider())
        with patch.dict(os.environ, {"KRAL_SOURCE_ROOT": ""}):
            with self.assertRaises(Denied) as err:
                gateway.route("/api/v1/owner/sources",
                              {"action": "inspect", "source_id": "a.apk"})
        self.assertEqual(err.exception.code, "SOURCE_ROOT_NOT_CONFIGURED")

    def test_gateway_rejects_extra_fields_not_forwarded(self):
        gateway = Gateway(object(), provider=DisabledProvider())
        with self.assertRaises(Denied) as err:
            gateway.route("/api/v1/owner/sources",
                          {"action": "inspect", "source_id": "a.apk",
                           "root": "/etc"})
        self.assertEqual(err.exception.code, "SOURCE_FIELDS_DENIED")

    def test_http_source_route_denies_missing_owner_proofs(self):
        gateway = Gateway(object(), provider=DisabledProvider())
        server = BoundedThreadingHTTPServer(
            ("127.0.0.1", 0), handler_for(gateway), max_workers=2)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", server.server_port,
                                           timeout=3)
            c.request("POST", "/api/v1/owner/sources",
                      '{"action":"inspect","source_id":"a.apk"}',
                      {"Content-Type": "application/json"})
            response = c.getresponse()
            self.assertIn(response.status, (403, 411, 503))
            self.assertNotEqual(response.status, 200)
            response.read()
            c.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
