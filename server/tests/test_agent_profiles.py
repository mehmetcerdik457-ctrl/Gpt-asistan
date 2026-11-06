"""Validate preserved KRAL Copilot profiles; no implicit external tool access."""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2] / ".github" / "agents"
EXPECTED = {
    "ai-ml-engineer", "android-engineer", "apk-forensic", "chief-engineer",
    "ci-cd-engineer", "cloud-engineer", "code-reviewer", "github-master-ai",
    "mcp-engineer", "release-engineer", "security-auditor", "test-engineer",
}


class CopilotAgentProfileTests(unittest.TestCase):
    def read(self, name):
        data = (ROOT / (name + ".agent.md")).read_text(encoding="utf-8")
        self.assertTrue(data.startswith("---\n"))
        fields = data.split("---\n", 2)[1]
        self.assertRegex(fields, r"(?m)^name: .+")
        self.assertRegex(fields, r"(?m)^description: .+")
        match = re.search(r"(?m)^tools: (\[.*\])\s*$", fields)
        self.assertIsNotNone(match)
        tools = json.loads(match.group(1))
        self.assertTrue(all(isinstance(x, str) for x in tools))
        self.assertEqual(len(tools), len(set(tools)))
        return data, tools

    def test_twelve_preserved_named_specialists(self):
        self.assertEqual(EXPECTED, {p.name.removesuffix(".agent.md")
                                   for p in ROOT.glob("*.agent.md")})
        for name in EXPECTED:
            with self.subTest(role=name):
                self.read(name)

    def test_readonly_roles_do_not_receive_edit_or_mutating_github_tools(self):
        for name in ("apk-forensic", "code-reviewer", "security-auditor", "release-engineer"):
            _, tools = self.read(name)
            self.assertNotIn("edit", tools)
            self.assertFalse(any(
                tool.startswith("github/") and any(verb in tool for verb in
                ("create", "update", "delete", "merge", "push", "workflow_dispatch"))
                for tool in tools
            ))

    def test_master_cannot_implicitly_launch_unavailable_youtube_mcp(self):
        text, tools = self.read("github-master-ai")
        self.assertNotIn("mcp-servers:", text)
        self.assertFalse(any(tool.startswith("youtube/") for tool in tools))
        self.assertIn("not activated", text)
        self.assertNotIn("COPILOT_MCP_YOUTUBE_REFRESH_TOKEN", text)


if __name__ == "__main__":
    unittest.main()
