import json
import unittest

import detect
import settings
from helpers import RepoTest


class SettingsTest(RepoTest):
    def test_invalid_values_and_scopes_are_rejected(self):
        self.assertIn("Invalid value", self.entry_json("config", "set", "browser", "sometimes", code=2)["reason"])
        self.assertIn("project setting", self.entry_json("config", "set", "runner", "ddev", code=2)["reason"])
        self.assertIn("Unknown setting", self.entry_json("config", "get", "nope", code=2)["reason"])

    def test_project_values_override_user_defaults(self):
        settings.store("browser", "visible")
        settings.store("browser", "background", self.repo)
        self.assertEqual(settings.load(None)["browser"], "visible")
        self.assertEqual(settings.load(self.repo)["browser"], "background")
        self.assertEqual(self.git("status", "--short").strip(), "")

    def test_corrupt_settings_fall_back_to_defaults(self):
        self.data.mkdir()
        settings.user_path().write_text("{")
        self.assertEqual(settings.load(None), settings.DEFAULTS)

    def test_only_packaged_profiles_are_valid(self):
        self.assertTrue(settings.valid("profile", "drupal"))
        self.assertTrue(settings.valid("profile", "laravel"))
        self.assertFalse(settings.valid("profile", "nope"))


class DetectTest(RepoTest):
    def write(self, relative, data):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if isinstance(data, dict) else data)

    def test_drupal_version_and_ddev_runner(self):
        self.write("composer.json", {"require": {"drupal/core-recommended": "^11"}})
        self.write("composer.lock", {"packages": [{"name": "drupal/core", "version": "11.2.3"}]})
        self.write(".ddev/config.yaml", "name: x\n")
        found = detect.detect(self.repo)
        self.assertEqual((found["profile"], found["version"], found["runner"], found["application"]),
                         ("drupal", "11", "ddev", "."))

    def test_subdirectory_application_and_ambiguity(self):
        self.write("site/composer.json", {"require": {"drupal/core": "^10"}})
        self.assertEqual(detect.detect(self.repo)["application"], "site")
        self.write("other/composer.json", {"require": {"drupal/core": "^10"}})
        found = detect.detect(self.repo)
        self.assertTrue(found["ambiguous"])
        self.assertIsNone(found["profile"])

    def test_non_drupal_project(self):
        self.write("package.json", {"name": "x"})
        self.assertEqual((detect.detect(self.repo)["profile"], detect.detect(self.repo)["runner"]), (None, "local"))


if __name__ == "__main__":
    unittest.main()
