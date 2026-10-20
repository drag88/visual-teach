"""Release checks: the plugin files agree with each other, with SKILL.md and with the changelog.

Usage: python3 test_release.py
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
        skill = re.search(r"^name: (\S+)$", read("SKILL.md"), re.M).group(1)
        self.assertEqual(skill, plugin["name"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
