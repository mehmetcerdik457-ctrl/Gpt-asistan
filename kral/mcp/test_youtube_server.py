import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("youtube_server.py")
SPEC = importlib.util.spec_from_file_location("kral_youtube", MODULE_PATH)
youtube = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(youtube)


class YouTubeMCPTests(unittest.TestCase):
    def setUp(self):
        youtube._TOKEN_CACHE["token"] = None
        youtube._TOKEN_CACHE["expires_at"] = 0.0

    def test_status_never_returns_secret_values(self):
        env = {
            "YOUTUBE_CLIENT_ID": "client-secret-value",
            "YOUTUBE_CLIENT_SECRET": "secret-value",
            "YOUTUBE_REFRESH_TOKEN": "refresh-secret-value",
            "YOUTUBE_WRITE_ENABLED": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            payload = youtube.status()
        serialized = json.dumps(payload)
        self.assertNotIn("client-secret-value", serialized)
        self.assertNotIn("secret-value", serialized)
        self.assertNotIn("refresh-secret-value", serialized)
        self.assertTrue(payload["client_id_configured"])
        self.assertTrue(payload["refresh_token_configured"])
        self.assertFalse(payload["write_enabled"])

    def test_write_tools_fail_closed_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                youtube.video_update_metadata({"video_id": "abc"})
            with self.assertRaises(RuntimeError):
                youtube.comment_moderate(
                    {"comment_id": "x", "moderation_status": "rejected"}
                )

    def test_tools_list_contains_read_and_guarded_write_tools(self):
        names = {tool["name"] for tool in youtube.TOOLS}
        self.assertIn("channel_get", names)
        self.assertIn("analytics_report", names)
        self.assertIn("video_update_metadata", names)
        self.assertIn("comment_moderate", names)

    def test_mcp_initialize_and_tool_list(self):
        init = youtube.handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        self.assertEqual(init["result"]["serverInfo"]["name"], "kral-youtube")
        listing = youtube.handle_rpc(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
        self.assertGreaterEqual(len(listing["result"]["tools"]), 8)

    def test_channel_get_uses_authenticated_mine_query(self):
        fake = {"items": [{"id": "channel-1", "snippet": {"title": "x"}}]}
        with patch.object(youtube, "api_request", return_value=fake) as mocked:
            result = youtube.own_channel()
        self.assertEqual(result["id"], "channel-1")
        params = mocked.call_args.kwargs["params"]
        self.assertEqual(params["mine"], "true")


if __name__ == "__main__":
    unittest.main()
