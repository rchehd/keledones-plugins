import json
import unittest

from helpers import RepoTest
import detect
import settings


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


class ProfileSelectionTest(RepoTest):
    def select(self, project=None, code=0):
        return self.entry_json("profiles", "--project", str(project or self.repo), code=code)

    def test_composes_profiles_at_the_same_and_nested_roots(self):
        (self.repo / "go.mod").write_text("module example.com/app\n")
        (self.repo / "pyproject.toml").write_text("[project]\nname = 'app'\n")
        child = self.repo / "apps" / "site"
        child.mkdir(parents=True)
        (child / "composer.json").write_text('{"require":{"drupal/core":"^10"}}')
        (child / "compose.yaml").write_text("services: {}\n")

        views = {(item["application"], item["profile"]): item for item in self.select()["profiles"]}
        self.assertEqual(set(views), {(".", "go"), (".", "python"), ("apps/site", "drupal")})
        self.assertEqual(views[("apps/site", "drupal")]["runner"], "compose")
        self.assertEqual(views[("apps/site", "drupal")]["evidence"], ["composer.json require drupal/core"])
        self.assertEqual(self.select(child)["profiles"], [views[("apps/site", "drupal")]])

    def test_legacy_config_is_one_explicit_selection(self):
        child = self.repo / "apps"
        child.mkdir()
        (self.repo / "go.mod").write_text("module example.com/app\n")
        self.entry_json("config", "set", "profile", "python", "--project", str(self.repo))
        self.entry_json("config", "set", "application", "apps", "--project", str(self.repo))
        self.entry_json("config", "set", "runner", "local", "--project", str(self.repo))
        selected, = self.select()["profiles"]
        self.assertEqual((selected["profile"], selected["application"], selected["source"]), ("python", "apps", "config"))

    def test_conflicting_php_frameworks_require_explicit_selection(self):
        (self.repo / "composer.json").write_text('{"require":{"laravel/framework":"^11","drupal/core":"^10"}}')
        result = self.select(code=2)
        self.assertEqual(result["conflicts"], [{"application": ".", "profiles": ["drupal", "laravel"]}])

    def test_multi_profile_config_validates_structure(self):
        item = dict(profile="python", application=".", runner="local")
        for invalid in ([item, item], [dict(item, application="../project")], [dict(item, runner=["local"])]):
            self.entry_json("config", "set", "profiles", json.dumps(invalid), "--project", str(self.repo), code=2)
        selected = [item, dict(item, profile="go")]
        self.entry_json("config", "set", "profiles", json.dumps(selected), "--project", str(self.repo))
        self.assertEqual([item["profile"] for item in self.select()["profiles"]], ["python", "go"])


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
        self.write("compose.yml", "services: {}\n")
        self.assertEqual((detect.detect(self.repo)["profile"], detect.detect(self.repo)["runner"]), ("generic", "local"))

    def test_explicit_unknown_profile_is_preserved(self):
        self.write(".ready-check.json", {"profile": "unavailable"})
        self.assertEqual(detect.detect(self.repo)["profile"], "unavailable")

    def test_generic_can_be_selected_for_a_mixed_project(self):
        self.write("go.mod", "module example.com/tool\n")
        self.write("pyproject.toml", '[project]\nname = "tool"\n')
        self.write(".ready-check.json", {"profile": "generic"})
        self.assertEqual(detect.detect(self.repo)["profile"], "generic")


if __name__ == "__main__":
    unittest.main()
