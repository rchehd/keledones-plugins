import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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
        settings.store("browser", "visible", self.repo)
        self.assertEqual(settings.load(self.repo)["browser"], "visible")
        self.assertEqual(self.git("status", "--short").strip(), "")

    def test_corrupt_settings_fall_back_to_defaults(self):
        self.data.mkdir()
        settings.user_path().write_text("{")
        self.assertEqual(settings.load(None), settings.DEFAULTS)

    def test_only_packaged_profiles_are_valid(self):
        self.assertTrue(settings.valid("profile", "drupal"))
        self.assertTrue(settings.valid("profile", "laravel"))
        self.assertFalse(settings.valid("profile", "nope"))

    def test_artifact_language_allows_parentheses_only(self):
        for value in ("Portuguese (Brazil)", "Chinese (Simplified)"):
            self.assertTrue(settings.valid("artifactLanguage", value))

        for value in ("English\n", "En;glish", 'En"glish', "En`glish`", "En$(id)", "a|b", "'English'"):
            self.assertFalse(settings.valid("artifactLanguage", value))

    def test_store_and_unset_take_the_settings_lock(self):
        with patch.object(settings, "migration_lock", wraps=settings.migration_lock) as lock:
            settings.store("browser", "visible")
            settings.unset("browser")

        self.assertEqual(lock.call_count, 2)

    def test_concurrent_stores_keep_every_key(self):
        code = ("import sys; sys.path.insert(0, %r); import settings; "
                "settings.store(sys.argv[1], sys.argv[2])" % str(Path(settings.__file__).parent))
        jobs = [("browser", "visible"), ("install", "auto"), ("artifactLanguage", "Polish")]

        for _ in range(5):
            settings.unset("browser")
            settings.unset("install")
            settings.unset("artifactLanguage")
            processes = [subprocess.Popen([sys.executable, "-B", "-c", code, *job]) for job in jobs]

            for process in processes:
                self.assertEqual(process.wait(), 0)

            self.assertEqual(json.loads(settings.user_path().read_text()),
                             {"browser": "visible", "install": "auto", "artifactLanguage": "Polish"})


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
        self.assertEqual(set(views), {(".", "go"), (".", "python"), ("apps/site", "drupal"), ("apps/site", "devops")})
        self.assertEqual(views[("apps/site", "drupal")]["runner"], "compose")
        self.assertEqual(views[("apps/site", "devops")]["runner"], "local")
        self.assertEqual(views[("apps/site", "drupal")]["evidence"], ["composer.json require drupal/core"])
        self.assertEqual(self.select(child)["profiles"], [views[("apps/site", "drupal")], views[("apps/site", "devops")]])

    def test_php_module_inside_the_same_application_is_not_a_second_selection(self):
        module = self.repo / "web/modules/custom/foo"
        module.mkdir(parents=True)
        (self.repo / "composer.json").write_text('{"require":{"drupal/core":"^10"}}')
        (module / "composer.json").write_text('{"require":{"drupal/core":"^10"}}')
        self.assertEqual([(item["profile"], item["application"]) for item in self.select()["profiles"]],
                         [("drupal", ".")])
        (module / ".ready-check.json").write_text('{"profile": "drupal"}')
        self.assertIn(("drupal", "web/modules/custom/foo"),
                      [(item["profile"], item["application"]) for item in self.select()["profiles"]])

    def test_a_profile_overridden_at_the_ancestor_does_not_hide_a_nested_application(self):
        site = self.repo / "apps/site"
        module = site / "modules/foo"
        module.mkdir(parents=True)
        (site / "composer.json").write_text('{"require":{"drupal/core":"^10"}}')
        (site / ".ready-check.json").write_text('{"profile": "generic"}')
        (module / "composer.json").write_text('{"require":{"drupal/core":"^10"}}')
        self.assertIn(("drupal", "apps/site/modules/foo"),
                      [(item["profile"], item["application"]) for item in self.select()["profiles"]])

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

    def test_profiles_use_separate_scope_and_results_in_one_task_folder(self):
        tools = self.repo / "tools"
        service = self.repo / "service"
        for directory in (tools, service):
            directory.mkdir()
        (service / "go.mod").write_text("module example.com/service\n")
        (tools / "config.json").write_text('{"enabled": false}\n')
        self.git("add", ".")
        self.git("commit", "-q", "-m", "Add applications")
        self.git("switch", "-q", "-c", "task")

        self.run_entry("consent", "no", "--project", str(self.repo), "--selection", "go:local:service",
                       "--selection", "generic:local:tools").check_returncode()
        (service / "README.md").write_text("# Service\n")
        (tools / "config.json").write_text('{"enabled": true}\n')
        (self.repo / "README.md").write_text("# Repository\n")
        report = self.entry_json("reports", "--project", str(self.repo), "--task", "Two applications")
        directory = Path(report["directory"])
        all_covered, outside = set(), set()
        for item in self.select()["profiles"]:
            profile, application = item["profile"], item["application"]
            args = ("--profile", profile, "--project", str(self.repo / application), "--base", "main")
            doctor_file, static_file = (directory / f"{action}-{profile}.json" for action in ("doctor", "static"))
            doctor = self.entry_json("doctor", *args, "--output", str(doctor_file))
            static = self.entry_json("static", *args, "--output", str(static_file))
            self.assertEqual(doctor["status"], "READY")
            self.assertTrue(static["can_proceed"])
            self.assertEqual(doctor["scope"]["snapshot"], static["scope"]["snapshot"])
            self.assertEqual(static["runner"], item["runner"])
            self.assertTrue(doctor_file.is_file() and static_file.is_file())
            all_covered.update(f"{application}/{path}" for path in static["scope"]["changed_files"])
            outside.update(static["scope"]["outside_scope"])
        self.assertEqual(all_covered, {"service/README.md", "tools/config.json"})
        self.assertEqual(outside - all_covered, {"README.md"})
        mismatch = self.entry_json("doctor", "--profile", "generic", "--project", str(service),
                                   "--base", "main", code=2)
        self.assertIn("conflict with project configuration", mismatch["reason"])

        (tools / "config.json").write_text('{"enabled": }\n')
        broken = self.entry_json("static", "--profile", "generic", "--project", str(tools),
                                 "--base", "main", "--output", str(directory / "static-generic-round-2.json"), code=1)
        self.assertFalse(broken["can_proceed"])
        self.assertIn("syntax", [check["id"] for check in broken["checks"] if check["status"] == "FAIL"])
        go = self.entry_json("static", "--profile", "go", "--project", str(service), "--base", "main")
        self.assertTrue(go["can_proceed"])

    def test_same_application_keeps_each_profiles_runner(self):
        (self.repo / "README.md").write_text("# Task\n")
        self.run_entry("consent", "no", "--project", str(self.repo), "--selection", "go:compose:.",
                       "--selection", "python:local:.").check_returncode()
        for profile, runner in (("go", "compose"), ("python", "local")):
            report = self.entry_json("doctor", "--profile", profile, "--project", str(self.repo),
                                     "--base", "main", env={"LINT_RUNNER": ""})
            self.assertEqual(report["runner"], runner)


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
        self.assertEqual((detect.detect(self.repo)["profile"], detect.detect(self.repo)["runner"]), ("devops", "local"))

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
