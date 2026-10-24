"""Static security checks for KRAL custom agents. NOT a live LLM jailbreak test."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / ".github" / "agents"
NAMES = (
    "github-master-ai", "chief-engineer", "android-engineer", "ai-ml-engineer",
    "mcp-engineer", "cloud-engineer", "ci-cd-engineer", "test-engineer",
    "security-auditor", "code-reviewer", "apk-forensic", "release-engineer",
)
# Canonical tool contract, captured from reviewed agent definitions on this branch.
# Changes require a deliberate review and test update; tools cannot drift silently.
APPROVED_TOOLS = {
    "github-master-ai": [
        "read",
        "search",
        "edit",
        "execute",
        "agent",
        "github/get_file_contents",
        "github/search_code",
        "github/pull_request_read",
        "youtube/status",
        "youtube/channel_get",
        "youtube/videos_list",
        "youtube/playlists_list",
        "youtube/comments_list",
        "youtube/analytics_report"
    ],
    "chief-engineer": [
        "read",
        "search",
        "edit",
        "execute",
        "agent"
    ],
    "android-engineer": [
        "read",
        "search",
        "edit",
        "execute",
        "agent"
    ],
    "ai-ml-engineer": [
        "read",
        "search",
        "edit",
        "execute",
        "agent"
    ],
    "mcp-engineer": [
        "read",
        "search",
        "edit",
        "execute",
        "agent"
    ],
    "cloud-engineer": [
        "read",
        "search",
        "edit",
        "execute",
        "agent"
    ],
    "ci-cd-engineer": [
        "read",
        "search",
        "edit",
        "execute"
    ],
    "test-engineer": [
        "read",
        "search",
        "edit",
        "execute"
    ],
    "security-auditor": [
        "read",
        "search",
        "github/get_file_contents",
        "github/search_code",
        "github/pull_request_read"
    ],
    "code-reviewer": [
        "read",
        "search",
        "github/get_file_contents",
        "github/search_code",
        "github/pull_request_read"
    ],
    "apk-forensic": [
        "read",
        "search",
        "execute",
        "github/get_file_contents",
        "github/search_code"
    ],
    "release-engineer": [
        "read",
        "search",
        "execute"
    ]
}

READ_ONLY = {"security-auditor", "code-reviewer", "apk-forensic", "release-engineer"}
SECRET = re.compile(r"(?:ghp_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{36,})")
UNSAFE = {"github/merge_pull_request", "github/delete_file", "github/update_ref"}


def validate(name, content):
    if not content.startswith("---\n") or "\n---\n" not in content[4:]:
        raise ValueError("missing frontmatter")
    front = content.split("\n---\n", 1)[0][4:]
    for field in ("name", "description"):
        if not re.search(r"(?m)^" + field + r":\s*\S", front):
            raise ValueError(field + " missing")
    m = re.findall(r"(?m)^tools:\s*(\[[^\n]*\])\s*$", front)
    if len(m) != 1:
        raise ValueError("invalid tool declaration")
    tools = json.loads(m[0])
    if not isinstance(tools, list) or not all(isinstance(x, str) for x in tools):
        raise ValueError("invalid tools")
    if len(set(tools)) != len(tools) or "*" in tools or UNSAFE.intersection(tools):
        raise ValueError("wildcard, duplicate or dangerous tool")
    if SECRET.search(content):
        raise ValueError("embedded secret")
    if name in APPROVED_TOOLS and tools != APPROVED_TOOLS[name]:
        raise ValueError("unexpected tool change against approved role profile")
    if name in READ_ONLY:
        if {"edit", "agent"}.intersection(tools):
            raise ValueError("read-only edit or delegation")
        allowed = {"github/get_file_contents", "github/search_code", "github/pull_request_read"}
        if any(t.startswith("github/") and t not in allowed for t in tools):
            raise ValueError("read-only GitHub write tool")
    if name == "github-master-ai":
        if "video_update_metadata" in front or "comment_moderate" in front:
            raise ValueError("unapproved YouTube write tool")
    return True


class GenesisAgentSecurityTests(unittest.TestCase):
    def test_twelve_real_agents(self):
        self.assertEqual({p.name for p in ROOT.glob("*.agent.md")},
                         {n + ".agent.md" for n in NAMES})
        for name in NAMES:
            with self.subTest(agent=name):
                self.assertTrue(validate(name, (ROOT / (name + ".agent.md")).read_text(encoding="utf-8")))

    def test_synthetic_escalation_blocked(self):
        cases = (
            ("security-auditor", '["read","agent"]'),
            ("security-auditor", '["read","edit"]'),
            ("apk-forensic", '["read","agent"]'),
            ("release-engineer", '["read","edit"]'),
            ("code-reviewer", '["read","github/update_ref"]'),
            ("chief-engineer", '["*"]'),
            ("ci-cd-engineer", '["read","github/merge_pull_request"]'),
            ("github-master-ai", '["read","youtube/comment_moderate"]'),
        )
        for role, tools in cases:
            with self.subTest(role=role, tools=tools):
                fake = "---\nname: Fake\ndescription: Fake profile\ntools: " + tools + "\n---\n"
                with self.assertRaises(ValueError):
                    validate(role, fake)

    def test_each_agent_rejects_a_synthetic_restricted_tool_escalation(self):
        # A separate negative case for each of the twelve roles. No commands
        # or external services are executed: only a fake YAML tool request.
        for role in NAMES:
            with self.subTest(role=role):
                fake = ('---\\nname: Fake\\ndescription: Synthetic attack\\n'
                        'tools: ["read","github/merge_pull_request"]\\n---\\n')
                fake = fake.replace('\\n', '\n')
                with self.assertRaises(ValueError):
                    validate(role, fake)

    def test_twelve_distinct_simulated_agent_escapes(self):
        # Contract-test only. Each case adds a different unauthorized tool to
        # that agent's reviewed file. No model or external system is invoked.
        attack_tools = {
          "github-master-ai": "youtube/video_update_metadata",
          "chief-engineer": "github/merge_pull_request",
          "android-engineer": "android/overwrite_original_apk",
          "ai-ml-engineer": "memory/export_private_records",
          "mcp-engineer": "mcp/*",
          "cloud-engineer": "cloud/create_billable_gpu",
          "ci-cd-engineer": "github/disable_workflow",
          "test-engineer": "tests/forge_pass",
          "security-auditor": "agent",
          "code-reviewer": "github/approve_pr",
          "apk-forensic": "apk/repack_original",
          "release-engineer": "release/publish_unverified"
}
        self.assertEqual(set(attack_tools), set(NAMES))
        for name, injected_tool in attack_tools.items():
            with self.subTest(role=name, attempted_tool=injected_tool):
                genuine = (ROOT / (name + ".agent.md")).read_text(encoding="utf-8")
                modified = genuine.replace("tools: [",
                                           "tools: [\"" + injected_tool + "\", ", 1)
                self.assertNotEqual(modified, genuine)
                with self.assertRaises(ValueError):
                    validate(name, modified)

    def test_synthetic_secret_and_missing_metadata_blocked(self):
        sample = "---\nname: Fake\ndescription: Fake profile\ntools: [\"read\"]\n---\n"
        with self.assertRaises(ValueError):
            validate("chief-engineer", sample + "ghp_" + ("A" * 36))
        for marker in ("name:", "description:", "tools:"):
            with self.subTest(marker=marker):
                with self.assertRaises(ValueError):
                    validate("chief-engineer", sample.replace(marker, "gone:"))


if __name__ == "__main__":
    unittest.main()
