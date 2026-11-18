import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("ready_check_package", PLUGIN / "scripts/validate-package.py")
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class PackageTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-package-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "package"
        skipped = PACKAGE.ignored(PLUGIN)
        shutil.copytree(PLUGIN, self.root, ignore=lambda folder, names: {
            name for name in names if name in {".git", "__pycache__"} or Path(folder) / name in skipped})

    def change_json(self, relative, change):
        path = self.root / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data))

    def assert_failed(self, check):
        result = PACKAGE.validate(self.root)
        self.assertEqual(result["status"], "FAIL", result)
        self.assertEqual(next(item for item in result["checks"] if item["id"] == check)["status"], "FAIL", result)

    def test_current_package_passes_from_another_directory(self):
        result = PACKAGE.validate(self.root)
        self.assertEqual(result["status"], "PASS", result)

    def test_version_mismatch_is_rejected(self):
        self.change_json(".codex-plugin/plugin.json", lambda data: data.update(version="9.9.9"))
        self.assert_failed("manifests")

    def test_missing_skill_is_rejected(self):
        (self.root / "skills/review/SKILL.md").unlink()
        self.assert_failed("skills")

    def test_missing_setup_skill_is_rejected(self):
        (self.root / "skills/setup/SKILL.md").unlink()
        self.assert_failed("skills")

    def test_codex_onboarding_cannot_point_at_task_verification(self):
        self.change_json(".codex-plugin/plugin.json", lambda data: data.update(onboardingSkill="./skills/check/SKILL.md"))
        self.assert_failed("manifests")

    def test_codex_import_requires_a_long_description(self):
        path = ".codex-plugin/plugin.json"
        self.change_json(path, lambda data: data["interface"].update(longDescription=" \t\n"))
        self.assert_failed("manifests")
        self.change_json(path, lambda data: data["interface"].pop("longDescription"))
        self.assert_failed("manifests")

    def test_missing_shared_entry_point_is_rejected(self):
        (self.root / "scripts/setup.sh").unlink()
        self.assert_failed("entry-points")

    def test_profile_entry_point_outside_profile_is_rejected(self):
        self.change_json("profiles/drupal/profile.json", lambda data: data["scripts"].update(setup="../../scripts/setup.py"))
        self.assert_failed("profiles")

    def test_symlink_resource_outside_package_is_rejected(self):
        path = self.root / "profiles/drupal/qa.md"
        path.unlink()
        external = self.root.parent / "external.md"
        external.write_text("External content\n")
        try:
            path.symlink_to(external)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        self.assert_failed("profiles")

    def test_stale_dependency_lock_is_rejected(self):
        self.change_json("dependencies/browser/package-lock.json", lambda data: data["packages"]["node_modules/@playwright/cli"].update(version="0.0.1"))
        self.assert_failed("dependencies")

    def test_mcp_cannot_use_a_different_browser_revision(self):
        self.change_json("dependencies/browser/package-lock.json", lambda data: data["packages"]["node_modules/@playwright/mcp"]["dependencies"].update({"playwright-core": "different"}))
        self.assert_failed("dependencies")

    def test_packaged_runtime_dependencies_are_rejected(self):
        (self.root / "dependencies/browser/node_modules").mkdir()
        self.assert_failed("dependencies")

    def test_broken_local_reference_is_rejected(self):
        with (self.root / "skills/check/SKILL.md").open("a") as stream:
            stream.write("\n[Missing guidance](references/missing.md)\n")
        self.assert_failed("local-links")


if __name__ == "__main__":
    unittest.main()
