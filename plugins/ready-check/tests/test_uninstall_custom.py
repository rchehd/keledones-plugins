import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import RepoTest
import customize
import uninstall
from project import BASE, LEGACY_BASE


class UninstallCustomTest(RepoTest):
    def plan(self, *flags):
        result = self.entry_json("uninstall", "--project", str(self.repo), "--dry-run", *flags)
        return {Path(item["path"]).name: item for item in result["items"]}

    def setUp(self):
        super().setUp()
        customize.add("rule", "Team rule", "project", self.repo)
        customize.add("review", "Item", "project", self.repo, "drupal", "D. Forms")
        self.entry_json("reports", "--project", str(self.repo), "--task", "Task")

    def test_customizations_and_reports_are_kept_by_default(self):
        items = self.plan()
        self.assertEqual({items[name]["action"] for name in ("rules.md", "extensions", "reports")}, {"keep"})

    def test_custom_flag_keeps_files_tracked_in_git(self):
        self.git("add", "-f", ".ai/ready-check/rules.md")
        items = self.plan("--custom")
        self.assertEqual(items["rules.md"]["action"], "keep")
        self.assertIn("git rm", items["rules.md"]["reason"])
        self.assertEqual(items["extensions"]["action"], "remove")

    def test_full_removal_clears_the_exclude_entry(self):
        self.entry_json("uninstall", "--project", str(self.repo), "--custom", "--reports")
        self.assertFalse((self.repo / ".ai/ready-check").exists())
        self.assertNotIn("/.ai/ready-check/", (self.repo / ".git/info/exclude").read_text())

    def legacy_parent_link(self):
        external = self.root / "external"
        external.mkdir()
        try:
            (self.repo / LEGACY_BASE.parent).symlink_to(external, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        return external

    def test_uninstall_skips_absent_legacy_storage_under_a_link(self):
        external = self.legacy_parent_link()
        outside = external / "keep.txt"
        outside.write_text("Keep\n", encoding="utf-8")
        self.entry_json("uninstall", "--project", str(self.repo), "--custom", "--reports")
        self.assertFalse((self.repo / BASE).exists())
        self.assertTrue((self.repo / LEGACY_BASE.parent).is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"), "Keep\n")

    def test_uninstall_refuses_to_follow_a_link_to_existing_legacy_storage(self):
        external = self.legacy_parent_link() / LEGACY_BASE.name
        external.mkdir()
        result = self.entry_json("uninstall", "--project", str(self.repo), "--custom", "--reports", code=2)
        self.assertIn("redirected directory", result["reason"])
        self.assertTrue(external.is_dir())
        self.assertTrue((self.repo / BASE).is_dir())

    def test_uninstall_plan_refuses_reparse_points_at_storage_root(self):
        for relative in (BASE, LEGACY_BASE):
            with self.subTest(storage=relative):
                root = self.repo / relative
                root.mkdir(parents=True, exist_ok=True)
                with patch("project.is_reparse_point", side_effect=lambda path: path == root):
                    with self.assertRaisesRegex(ValueError, "redirected directory"):
                        uninstall.plan(self.repo, reports=True, data=False, custom=True)


if __name__ == "__main__":
    unittest.main()
