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
