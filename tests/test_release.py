"""Release checks: the plugin files agree with each other, with SKILL.md and with the changelog.

Usage: python3 tests/test_release.py
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "visual-teach"


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class ReleaseTest(unittest.TestCase):
    def test_plugin_version_is_the_latest_changelog_entry(self):
        # Claude Code updates plugin installs only when this version changes, so a release that skips it reaches nobody.
        version = json.loads(read(".claude-plugin/plugin.json"))["version"]
        changelog = read("CHANGELOG.md")
        latest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M)
        self.assertIsNotNone(latest, "CHANGELOG.md has no release heading")
        self.assertEqual(version, latest.group(1))
        self.assertIn(f"[{version}]: https://github.com/drag88/visual-teach/", changelog, "the new heading needs its link")

    def test_marketplace_serves_this_plugin_from_the_repo_root(self):
        plugin = json.loads(read(".claude-plugin/plugin.json"))
        market = json.loads(read(".claude-plugin/marketplace.json"))
        self.assertEqual([(p["name"], p["source"]) for p in market["plugins"]], [(plugin["name"], ".")])
        skill = re.search(r"^name: (\S+)$", (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"), re.M).group(1)
        self.assertEqual(skill, plugin["name"])

    def test_skill_folder_follows_the_agent_skills_layout(self):
        # Claude Code plugins, npx skills and skills.sh all look for skills/<name>/SKILL.md, and the Agent Skills
        # spec wants the folder named after the skill. npx skills installs only this folder, so it carries the licence.
        skill = re.search(r"^name: (\S+)$", (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"), re.M).group(1)
        self.assertEqual(skill, SKILL_DIR.name)
        self.assertFalse((ROOT / "SKILL.md").exists(), "a root SKILL.md would shadow skills/ for npx skills")
        self.assertEqual((SKILL_DIR / "LICENSE").read_text(encoding="utf-8"), read("LICENSE"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
