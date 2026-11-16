import unittest

import customize
from helpers import RepoTest


class UninstallCustomTest(RepoTest):
    def plan(self, *flags):
        result = self.entry_json("uninstall", "--project", str(self.repo), "--dry-run", *flags)
        return {item["path"].rsplit("/", 1)[-1]: item for item in result["items"]}

    def setUp(self):
        super().setUp()
        customize.add("rule", "Team rule", "project", self.repo)
        customize.add("review", "Item", "project", self.repo, "drupal", "D. Forms")
        self.entry_json("reports", "--project", str(self.repo), "--task", "Task")

    def test_customizations_and_reports_are_kept_by_default(self):
        items = self.plan()
        self.assertEqual({items[name]["action"] for name in ("rules.md", "extensions", "reports")}, {"keep"})

    def test_custom_flag_keeps_files_tracked_in_git(self):
        self.git("add", "-f", "ai/ready-check/rules.md")
        items = self.plan("--custom")
        self.assertEqual(items["rules.md"]["action"], "keep")
        self.assertIn("git rm", items["rules.md"]["reason"])
        self.assertEqual(items["extensions"]["action"], "remove")

    def test_full_removal_clears_the_exclude_entry(self):
        self.entry_json("uninstall", "--project", str(self.repo), "--custom", "--reports")
        self.assertFalse((self.repo / "ai/ready-check").exists())
        self.assertNotIn("/ai/ready-check/", (self.repo / ".git/info/exclude").read_text())


if __name__ == "__main__":
    unittest.main()
