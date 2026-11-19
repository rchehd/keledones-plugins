import json
import os
import unittest
from unittest.mock import patch

from helpers import RepoTest
import customize
import rules


class CustomizeTest(RepoTest):
    def add(self, text, kind="review", scope="project", section="D. Forms", must=False):
        return customize.add(kind, text, scope, self.repo, "drupal", section, must)

    def test_same_item_is_added_once(self):
        self.assertTrue(self.add("Forms keep values")[1])
        self.assertFalse(self.add("  forms   keep values ")[1])
        text = (self.repo / ".ai/ready-check/extensions/drupal/review.md").read_text()
        self.assertEqual(text.count("Forms keep values"), 1)
        self.assertIn("## D. Forms", text)

    def test_remove_prefers_exact_item_and_refuses_ambiguous_text(self):
        self.add("Use DI")
        self.add("Use DI in forms")
        customize.remove("review", "Use DI", "project", self.repo, "drupal")
        text = (self.repo / ".ai/ready-check/extensions/drupal/review.md").read_text()
        self.assertIn("Use DI in forms", text)
        self.add("Use DI in services")
        with self.assertRaisesRegex(ValueError, "2 items match"):
            customize.remove("review", "Use DI in", "project", self.repo, "drupal")

    def test_section_text_cannot_inject_items(self):
        self.add("Item", section="X\n- [ ] injected")
        items = customize.load(self.repo, "review", "drupal")
        self.assertEqual([item["text"] for item in items], ["Item"])

    def test_project_disable_hides_global_item_and_client_rule(self):
        customize.add("rule", "Prefer switch", "global")
        with patch.dict(os.environ, {"CLAUDE_PLUGIN_OPTION_RULES": "No else after return"}):
            customize.set_disabled("prefer switch", "project", self.repo, True)
            customize.set_disabled("No else after return", "project", self.repo, True)
            self.assertEqual(rules.load(self.repo), [])
            self.assertTrue(all(item["disabled"] for item in customize.load(self.repo, "rule")))
            self.assertEqual(len(rules.load(None)), 2)
        path, note = customize.set_disabled("prefer switch", "project", self.repo, False)
        self.assertIsNone(note)

    def test_project_enable_reports_global_disable(self):
        customize.add("rule", "Global rule", "global")
        customize.set_disabled("Global rule", "global", None, True)
        self.assertIn("globally", customize.set_disabled("Global rule", "project", self.repo, False)[1])

    def test_malformed_disabled_list_is_ignored(self):
        self.add("Item")
        disabled = self.repo / ".ai/ready-check/disabled.json"
        for content in ("[1, 2]", '{"hashes": 5}', "{"):
            disabled.write_text(content)
            customize.set_disabled("Item", "project", self.repo, True)
            self.assertEqual(json.loads(disabled.read_text())["hashes"], [rules.item_hash("Item")])

    def test_symlinked_parent_is_refused(self):
        target = self.root / "elsewhere"
        target.mkdir()
        (self.repo / ".ai/ready-check").mkdir(parents=True)
        try:
            (self.repo / ".ai/ready-check/extensions").symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.add("Item")
        self.assertEqual(list(target.iterdir()), [])

    def test_bare_rule_is_deduplicated_and_must_upgrades(self):
        path = self.repo / ".ai/ready-check/rules.md"
        path.parent.mkdir(parents=True)
        path.write_text("Prefer switch\n")
        self.assertFalse(customize.add("rule", "prefer switch", "project", self.repo)[1])
        self.assertEqual(customize.add("rule", "Prefer switch", "project", self.repo, must=True)[1], "upgraded")
        self.assertEqual(path.read_text(), "- MUST: Prefer switch\n")

    def test_cli_requires_scope_and_keeps_files_excluded(self):
        result = self.entry_json("customize", "add", "Item", "--kind", "qa", "--project", str(self.repo), code=2)
        self.assertIn("--scope", result["reason"])
        self.entry_json("customize", "add", "Item", "--kind", "qa", "--scope", "project", "--profile", "drupal",
                        "--section", "Forms", "--project", str(self.repo))
        self.assertEqual(self.git("status", "--short").strip(), "")


if __name__ == "__main__":
    unittest.main()
