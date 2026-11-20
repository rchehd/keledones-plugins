import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
from dependency_support import asset_id, bundle_path
ENTRY = PLUGIN / "scripts/check-profile.py"
TOOL = '''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
name = Path(sys.argv[0]).name
if "--version" in sys.argv:
    print("2.3.5" if name == "phpstan" else "3.13.6")
    sys.exit(0)
mode = os.environ.get("READY_CHECK_TEST_" + name.upper(), "pass")
if mode == "timeout":
    time.sleep(10)
if mode == "invalid":
    print("not a report")
    sys.exit(0)
if name == "phpstan" and os.environ.get("READY_CHECK_TEST_ARGS"):
    Path(os.environ["READY_CHECK_TEST_ARGS"]).write_text(json.dumps(sys.argv[1:]))
if mode == "drift":
    with open("web/modules/custom/demo/demo.php", "a") as stream:
        stream.write("\\n")
messages = {}
if mode in ("error", "warning", "old"):
    file = os.environ.get("READY_CHECK_TEST_FILE") or ("web/modules/custom/demo/caller.php" if name == "phpstan" else "web/modules/custom/demo/demo.php")
    message = dict(line=int(os.environ.get("READY_CHECK_TEST_LINE", 1 if mode == "old" else 3)), message="Fixture finding", type="WARNING" if mode == "warning" else "ERROR")
    messages[str(Path(file).resolve())] = dict(messages=[message])
print(json.dumps(dict(files=messages, errors=[])))
sys.exit(3 if mode == "crash" else 2 if mode == "warning" else 1 if messages else 0)
'''


@unittest.skipUnless(shutil.which("php") and shutil.which("git"), "PHP and Git are required")
class StaticChecksTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("LINT_", "READY_CHECK_TEST_"))}
        self.env["LINT_RUNNER"] = "local"
        self.env["READY_CHECK_DATA_DIR"] = str(self.root / "data")
        self.git("init", "-b", "main")
        self.write(".gitignore", "vendor/\nnode_modules/\nignored.php\n")
        self.write("composer.json", '{"require":{"drupal/core":"^10"}}\n')
        self.write("phpstan.neon", "parameters:\n  level: 0\n  paths:\n    - web/modules/custom\n")
        self.write("web/modules/custom/demo/demo.php", "<?php\n\nfunction demo() {}\n")
        self.write("web/modules/custom/demo/caller.php", "<?php\n\nfunction caller() {}\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "Fixture")
        self.write("vendor/autoload.php", "<?php\n")
        for name in ("phpcs", "phpstan"):
            path = self.write("vendor/bin/" + name, TOOL)
            path.chmod(0o755)
        self.write("web/modules/custom/demo/demo.php", "<?php\n\nfunction demo() { return 1; }\n")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.project, env=self.env,
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout

    def write(self, name, content):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def check(self, action="static", extra=(), project=None, scope=("--base", "main")):
        process = subprocess.run([sys.executable, str(ENTRY), action, "--profile", "drupal", "--project",
                                  str(project or self.project), *extra, *scope],
                                 env=self.env, capture_output=True, text=True, encoding="utf-8")
        data = json.loads(process.stdout)
        if data.get("evidence_directory"):
            self.addCleanup(shutil.rmtree, data["evidence_directory"], True)
        self.assertEqual(process.returncode, {"PASS": 0, "N/A": 0, "FAIL": 1, "INCOMPLETE": 2, "READY": 0, "MISSING": 2}[data["status"]])
        self.assertEqual("can_proceed" in data, action == "static")
        return data

    def checker(self, result, name):
        return next(c for c in result["checks"] if c["id"] == name)

    def managed_tools(self):
        source = PLUGIN / "profiles/drupal/tools"
        folder = bundle_path(source, self.root / "data", "profiles/drupal")
        shutil.copytree(source, folder)
        (folder / "ready.json").write_text(json.dumps(dict(asset_id=asset_id(source))))
        self.write("web/core/lib/Drupal.php", "<?php class Drupal { const VERSION = '10.6.0'; }\n")
        for name in ("phpcs", "phpstan"):
            path = folder / "vendor/bin" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(TOOL)
            path.chmod(0o755)
        binary = folder / "node_modules/.bin/eslint"
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/usr/bin/env python3\nimport sys\nprint("9.39.5" if "--version" in sys.argv else "[]")\n')
        binary.chmod(0o755)
        return folder

    def test_managed_tools_fill_missing_checkers_without_project_dependency_changes(self):
        self.managed_tools()
        before = (self.project / "composer.json").read_bytes()
        shutil.rmtree(self.project / "vendor/bin")
        result = self.check()
        self.assertEqual(result["status"], "PASS", result)
        for name in ("phpcs", "phpstan"):
            self.assertEqual(self.checker(result, name)["tools"][0]["source"], "profile")
        self.assertEqual((self.project / "composer.json").read_bytes(), before)
        self.assertFalse((self.project / "vendor/bin").exists())

    def test_project_tools_take_priority_and_allow_mixed_sources(self):
        self.managed_tools()
        (self.project / "vendor/bin/phpcs").unlink()
        result = self.check("doctor")
        self.assertEqual(result["status"], "READY", result)
        self.assertEqual(self.checker(result, "phpcs")["tools"][0]["source"], "profile")
        self.assertEqual(self.checker(result, "phpstan")["tools"][0]["source"], "project")

    def test_broken_project_tool_does_not_fall_back_to_managed_tool(self):
        self.managed_tools()
        self.env["READY_CHECK_TEST_PHPCS"] = "crash"
        result = self.check()
        self.assertEqual(self.checker(result, "phpcs")["status"], "INCOMPLETE", result)
        self.assertEqual(self.checker(result, "phpcs")["tools"][0]["source"], "project")

    def test_managed_defaults_handle_missing_javascript_config(self):
        self.managed_tools()
        self.write("new.js", "const value = 1;\n")
        result = self.check()
        self.assertEqual(self.checker(result, "js")["status"], "PASS", result)
        tool = self.checker(result, "js")["tools"][0]
        self.assertEqual(tool["source"], "profile")
        self.assertEqual(tool["configuration"]["source"], "profile")
        self.assertFalse((self.project / "node_modules").exists())

    def test_ambiguous_project_configs_are_not_replaced_with_defaults(self):
        self.managed_tools()
        for directory in ("one", "two"):
            self.write(directory + "/eslint.config.js", "export default [];\n")
            self.write(directory + "/code.js", "const value = 1;\n")
        result = self.check("doctor")
        self.assertEqual(self.checker(result, "js")["status"], "MISSING", result)

    def test_modified_managed_configuration_invalidates_bundle(self):
        folder = self.managed_tools()
        (self.project / "vendor/bin/phpcs").unlink()
        (folder / "eslint.config.mjs").write_text("export default [];\n")
        result = self.check("doctor")
        self.assertEqual(self.checker(result, "phpcs")["status"], "MISSING", result)
        self.assertIn("configuration changed", self.checker(result, "phpcs")["reason"])

    def test_managed_tools_reject_unsupported_drupal_version(self):
        self.managed_tools()
        self.write("web/core/lib/Drupal.php", "<?php class Drupal { const VERSION = '9.5.0'; }\n")
        (self.project / "vendor/bin/phpcs").unlink()
        result = self.check("doctor")
        self.assertEqual(self.checker(result, "phpcs")["status"], "MISSING", result)
        self.assertIn("Drupal 10/11", self.checker(result, "phpcs")["reason"])

    def test_effective_tool_version_changes_snapshot(self):
        first = self.check("doctor")["scope"]["snapshot"]
        binary = self.project / "vendor/bin/phpcs"
        binary.write_text(TOOL.replace('else "3.13.6"', 'else "3.13.7"'))
        second = self.check("doctor")["scope"]["snapshot"]
        self.assertNotEqual(first, second)

    def test_clean_php_and_advisory_missing_tools(self):
        result = self.check()
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(result["can_proceed"])
        self.assertEqual(self.checker(result, "phpmd")["status"], "INCOMPLETE")
        self.assertFalse(self.checker(result, "phpmd")["required"])
        self.assertFalse(list(self.project.glob(".ready-check-lint.*")))

    def test_missing_required_tool_is_incomplete(self):
        (self.project / "vendor/bin/phpcs").unlink()
        result = self.check()
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse(result["can_proceed"])

    def test_doctor_does_not_run_linters(self):
        self.env["READY_CHECK_TEST_PHPCS"] = "timeout"
        result = self.check("doctor")
        self.assertEqual(result["status"], "READY", result)
        self.assertEqual(self.checker(result, "phpcs")["status"], "READY")
        self.assertEqual(self.checker(result, "phpcs")["evidence"], [])

    def test_syntax_error_blocks(self):
        self.write("web/modules/custom/demo/demo.php", "<?php function broken( {\n")
        result = self.check()
        self.assertEqual(result["status"], "FAIL", result)
        self.assertEqual(self.checker(result, "syntax")["status"], "FAIL")

    def test_debug_finding_has_location(self):
        self.write("web/modules/custom/demo/demo.php", "<?php\n\nvar_dump(1);\n")
        result = self.check()
        finding = self.checker(result, "debug")["findings"][0]
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(finding["line"], 3)

    def test_warning_does_not_block(self):
        self.env["READY_CHECK_TEST_PHPCS"] = "warning"
        result = self.check()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(self.checker(result, "phpcs")["findings"][0]["severity"], "warning")

    def test_existing_style_error_outside_changed_lines_is_filtered(self):
        self.env["READY_CHECK_TEST_PHPCS"] = "old"
        result = self.check()
        self.assertEqual(self.checker(result, "phpcs")["status"], "PASS", result)

    def test_phpstan_is_diff_only_with_project_config(self):
        self.env["READY_CHECK_TEST_PHPSTAN"] = "error"
        arguments = self.root / "phpstan-args.json"
        self.env["READY_CHECK_TEST_ARGS"] = str(arguments)
        result = self.check()
        self.assertEqual(self.checker(result, "phpstan")["status"], "PASS", result)
        args = json.loads(arguments.read_text(encoding="utf-8"))
        self.assertIn("web/modules/custom/demo/demo.php", args)
        self.assertNotIn("web/modules/custom/demo", args)
        self.assertTrue(args[args.index("-c") + 1].endswith("phpstan.neon"))

    def test_phpstan_reports_findings_on_changed_lines(self):
        self.env["READY_CHECK_TEST_PHPSTAN"] = "error"
        self.env["READY_CHECK_TEST_FILE"] = "web/modules/custom/demo/demo.php"
        result = self.check()
        self.assertEqual(self.checker(result, "phpstan")["status"], "FAIL", result)
        self.env["READY_CHECK_TEST_LINE"] = "1"
        self.assertEqual(self.checker(self.check(), "phpstan")["status"], "PASS")

    def test_invalid_report_and_tool_crash_never_pass(self):
        for mode in ("invalid", "crash"):
            with self.subTest(mode=mode):
                self.env["READY_CHECK_TEST_PHPCS"] = mode
                result = self.check()
                self.assertEqual(self.checker(result, "phpcs")["status"], "INCOMPLETE")
                self.assertFalse(result["can_proceed"])

    def test_untracked_ignored_and_space_paths(self):
        self.write("web/modules/custom/demo/space name.php", "<?php\nfunction extra() {}\n")
        self.write("ignored.php", "<?php broken(\n")
        result = self.check()
        self.assertEqual(result["status"], "PASS", result)
        self.assertIn("web/modules/custom/demo/space name.php", result["scope"]["files"])
        self.assertNotIn("ignored.php", result["scope"]["files"])

    def test_full_static_run_in_unicode_project_path(self):
        destination = self.root / "Mon Drupal é & site"
        self.project.rename(destination)
        self.project = destination
        result = self.check()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["scope"]["project"], str(destination.resolve()))

    @unittest.skipIf(os.name == "nt", "Unix PATH isolation; native Windows is covered by the OS matrix")
    def test_static_does_not_require_bash_or_gnu_grep(self):
        binaries = self.root / "runtime"
        binaries.mkdir()
        for name in ("git", "php"):
            (binaries / name).symlink_to(shutil.which(name))
        self.env["PATH"] = str(binaries)
        self.write("web/modules/custom/demo/demo.php", "<?php\n\nvar_dump(1);\n")
        result = self.check()
        self.assertEqual(self.checker(result, "debug")["status"], "FAIL", result)
        self.assertEqual(self.checker(result, "phpcs")["status"], "PASS", result)
        self.assertEqual(self.checker(result, "syntax")["status"], "PASS", result)

    def test_snapshot_changes_with_untracked_contents(self):
        path = self.write("new.php", "<?php\n")
        first = self.check("doctor")["scope"]["snapshot"]
        path.write_text("<?php\n\n")
        second = self.check("doctor")["scope"]["snapshot"]
        self.assertNotEqual(first, second)

    def test_documentation_only_needs_no_php_vendor(self):
        self.git("restore", "web/modules/custom/demo/demo.php")
        shutil.rmtree(self.project / "vendor")
        self.write("README.md", "# Documentation\n")
        result = self.check()
        self.assertEqual(result["status"], "N/A", result)

    def test_javascript_missing_config_does_not_pass(self):
        self.write("new.js", "const value = 1;\n")
        result = self.check()
        self.assertEqual(self.checker(result, "js")["status"], "INCOMPLETE")
        self.assertFalse(result["can_proceed"])

    def test_deleted_php_does_not_run_phpstan(self):
        self.git("restore", "web/modules/custom/demo/demo.php")
        (self.project / "web/modules/custom/demo/demo.php").unlink()
        result = self.check()
        self.assertEqual(self.checker(result, "phpstan")["status"], "N/A", result)
        self.assertEqual(self.checker(result, "syntax")["status"], "N/A")

    def test_invalid_base_and_conflicting_profile_are_incomplete(self):
        self.assertEqual(self.check(scope=("--base", "does-not-exist"))["status"], "INCOMPLETE")
        self.write(".ready-check.json", '{"profile":"another"}\n')
        self.assertEqual(self.check()["status"], "INCOMPLETE")

    def test_result_cannot_be_saved_inside_project(self):
        result = self.check(extra=("--output", str(self.project / "static.json")))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse((self.project / "static.json").exists())

    def test_timeout_and_code_drift_invalidate_gate(self):
        self.env["READY_CHECK_TEST_PHPCS"] = "timeout"
        result = self.check(extra=("--timeout", "1"))
        self.assertEqual(self.checker(result, "phpcs")["status"], "INCOMPLETE")
        self.env["READY_CHECK_TEST_PHPCS"] = "pass"
        self.env["READY_CHECK_TEST_PHPSTAN"] = "drift"
        result = self.check()
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("changed during", result["reason"])

    def test_unavailable_runner_does_not_fall_back_to_local(self):
        binary = self.root / "bin/ddev"
        binary.parent.mkdir()
        binary.write_text("#!/usr/bin/env bash\nexit 1\n")
        binary.chmod(0o755)
        self.env["PATH"] = str(binary.parent) + os.pathsep + self.env["PATH"]
        self.env["LINT_RUNNER"] = "ddev"
        result = self.check("doctor")
        self.assertEqual(result["status"], "MISSING")
        self.assertEqual(result["runner"], "ddev")

    def test_missing_yaml_parser_is_incomplete(self):
        self.write("web/modules/custom/demo/demo.info.yml", "name: Demo\n")
        result = self.check("doctor")
        self.assertEqual(self.checker(result, "syntax")["status"], "MISSING")

    def test_yaml_parse_failure_is_a_code_finding(self):
        self.write("vendor/autoload.php", """<?php
namespace Symfony\\Component\\Yaml\\Exception;
class ParseException extends \\RuntimeException {}
namespace Symfony\\Component\\Yaml;
class Yaml {
  public static function parseFile($file) {
    if (str_contains(file_get_contents($file), 'INVALID')) {
      throw new \\Symfony\\Component\\Yaml\\Exception\\ParseException('Invalid YAML');
    }
  }
}
""")
        path = self.write("web/modules/custom/demo/demo.info.yml", "name: Demo\n")
        self.assertEqual(self.checker(self.check(), "syntax")["status"], "PASS")
        path.write_text("INVALID\n")
        result = self.check()
        self.assertEqual(self.checker(result, "syntax")["status"], "FAIL", result)
        self.assertIn("Invalid YAML", self.checker(result, "syntax")["findings"][0]["message"])

    def test_config_finding_blocks(self):
        self.write("web/modules/custom/demo/config/install/demo.settings.yml", "uuid: fixture\n")
        result = self.check()
        self.assertEqual(self.checker(result, "config")["status"], "FAIL", result)
        self.assertEqual(result["status"], "FAIL")

    def test_external_output_is_persisted(self):
        output = self.root / "reports/static.json"
        result = self.check(extra=("--output", str(output)))
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)

    def test_monorepo_records_outside_changes(self):
        app = self.project / "apps/site"
        app.mkdir(parents=True)
        (app / "README.md").write_text("# Application\n")
        result = self.check(project=app)
        self.assertEqual(result["status"], "N/A", result)
        self.assertIn("web/modules/custom/demo/demo.php", result["scope"]["outside_scope"])

    def test_composer_process_crash_is_incomplete(self):
        binary = self.root / "bin/composer"
        binary.parent.mkdir()
        binary.write_text("#!/usr/bin/env bash\nexit 127\n")
        binary.chmod(0o755)
        self.env["PATH"] = str(binary.parent) + os.pathsep + self.env["PATH"]
        self.write("composer.json", '{"require":{"drupal/core":"^11"}}\n')
        result = self.check()
        self.assertEqual(self.checker(result, "composer")["status"], "INCOMPLETE", result)

    def commit(self, message):
        self.git("add", "-A")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def history(self):
        demo = "web/modules/custom/demo/demo.php"
        self.git("checkout", "--", demo)
        self.write(demo, "<?php\n\nfunction demo() { return 2; }\n")
        first = self.commit("Task one")
        self.write(demo, "<?php\n\nfunction demo() { return 2; }\nfunction foreign() {}\n")
        foreign = self.commit("Foreign")
        self.write(demo, "<?php\n\nfunction demo() { return 2; }\nfunction foreign() {}\nfunction mine() {}\n")
        second = self.commit("Task two")
        self.write(demo, self.project.joinpath(demo).read_text() + "function dirty() {}\n")
        return first, foreign, second

    def lines_kept(self, scope, line):
        self.env["READY_CHECK_TEST_PHPCS"] = "error"
        self.env["READY_CHECK_TEST_LINE"] = str(line)
        result = self.check(scope=scope)
        return bool(self.checker(result, "phpcs")["findings"])

    def test_commits_mode_filters_foreign_lines_and_keeps_uncommitted(self):
        first, foreign, second = self.history()
        self.write("other.txt", "x\n")
        scope = ("--commits", first, second, first)
        result = self.check(scope=scope)
        self.assertEqual(result["scope"]["mode"], "commits")
        self.assertEqual(result["scope"]["commits"], [first, second])
        self.assertIsNone(result["scope"]["base"])
        self.assertIsNone(result["scope"]["merge_base"])
        self.assertEqual(result["scope"]["changed_files"], ["web/modules/custom/demo/demo.php"])
        self.assertEqual(result["scope"]["uncommitted_outside_task"], ["other.txt"])
        self.assertTrue(self.lines_kept(scope, 3))
        self.assertFalse(self.lines_kept(scope, 4))
        self.assertTrue(self.lines_kept(scope, 5))
        self.assertTrue(self.lines_kept(scope, 6))
        self.assertTrue(self.lines_kept(("--commits", foreign), 4))

    def test_commits_mode_digest_ignores_foreign_uncommitted_files(self):
        first, _, second = self.history()
        scope = ("--commits", first, second)
        before = self.check("doctor", scope=scope)["scope"]["snapshot"]
        self.write("other.txt", "x\n")
        self.assertEqual(self.check("doctor", scope=scope)["scope"]["snapshot"], before)
        self.write("web/modules/custom/demo/demo.php", self.project.joinpath("web/modules/custom/demo/demo.php").read_text() + "\n")
        self.assertNotEqual(self.check("doctor", scope=scope)["scope"]["snapshot"], before)

    def test_commits_mode_rejects_non_ancestor(self):
        self.git("checkout", "--", "web/modules/custom/demo/demo.php")
        self.git("checkout", "-b", "side")
        self.write("side.txt", "x\n")
        side = self.commit("Side")
        self.git("checkout", "main")
        result = self.check(scope=("--commits", side))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("ancestor", result["reason"])

    def test_base_and_commits_are_mutually_exclusive_and_required(self):
        for scope in (("--base", "main", "--commits", "HEAD"), ()):
            process = subprocess.run([sys.executable, str(ENTRY), "doctor", "--profile", "drupal", "--project",
                                      str(self.project), *scope], env=self.env, capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)

    def test_ready_check_data_is_ignored(self):
        self.write(".ai/ready-check/note.php", "<?php\n")
        first = self.check("doctor")
        self.write(".ai/ready-check/note.php", "<?php\n\n")
        self.write(".ai/ready-check/evidence/log.txt", "x\n")
        second = self.check("doctor")
        self.assertEqual(first["scope"]["snapshot"], second["scope"]["snapshot"])
        self.assertNotIn(".ai/ready-check/note.php", second["scope"]["files"] + second["scope"]["changed_files"])

    def test_legacy_root_temporary_directories_are_out_of_scope(self):
        self.write(".ready-check-lint.legacy/config.php", "<?php\n")
        scope = self.check("doctor")["scope"]
        self.assertFalse([path for path in scope["files"] + scope["changed_files"] if path.startswith(".ready-check-lint.")])

    def test_scaffolded_core_linter_config_is_ignored(self):
        self.managed_tools()
        self.write("web/.eslintrc.json", '{"extends": "./core/.eslintrc.json"}\n')
        self.write("web/modules/custom/demo/new.js", "const value = 1;\n")
        result = self.check("doctor")
        tool = self.checker(result, "js")["tools"][0]
        self.assertEqual(self.checker(result, "js")["status"], "READY", result)
        self.assertEqual(tool["configuration"]["source"], "profile")

    def test_core_extending_config_with_project_rules_is_preserved(self):
        self.managed_tools()
        self.write("web/.eslintrc.json", json.dumps({"extends": "./core/.eslintrc.json", "rules": {"eqeqeq": "error"}}))
        self.write("web/modules/custom/demo/new.js", "const value = 1;\n")
        result = self.check("doctor")
        tool = self.checker(result, "js")["tools"][0]
        self.assertEqual(tool["configuration"]["source"], "project", result)
        self.assertEqual(tool["configuration"]["path"], "web/.eslintrc.json")

    def test_core_and_custom_extends_are_preserved(self):
        self.managed_tools()
        self.write("web/.eslintrc.json", json.dumps({"extends": ["./core/.eslintrc.json", "./custom-rules.json"]}))
        self.write("web/modules/custom/demo/new.js", "const value = 1;\n")
        result = self.check("doctor")
        self.assertEqual(self.checker(result, "js")["tools"][0]["configuration"]["source"], "project", result)

    def test_static_preserves_temporary_directories_of_other_runs(self):
        active = [self.project / ".ai/ready-check/tmp/.ready-check-lint.active",
                  self.project / ".ready-check-lint.legacy"]
        for path in active:
            path.mkdir(parents=True)
            (path / "config.xml").write_text("Active run config", encoding="utf-8")
        self.assertEqual(self.check()["status"], "PASS")
        for path in active:
            self.assertEqual((path / "config.xml").read_text(encoding="utf-8"), "Active run config")

    def test_static_cannot_clean_through_symlinked_data_parent(self):
        external = self.root / "other-toolkit"
        active = external / "ready-check/tmp/.ready-check-lint.active"
        active.mkdir(parents=True)
        (active / "keep.txt").write_bytes(b"Other toolkit data")
        try:
            (self.project / ".ai").symlink_to(external, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        self.check()
        self.assertEqual((active / "keep.txt").read_bytes(), b"Other toolkit data")

    def test_container_temporary_path_refuses_symlinked_ancestors(self):
        from types import SimpleNamespace
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
        sys.path.insert(0, str(PLUGIN / "profiles/drupal/scripts"))
        from core_checks import Lint
        from spec import SPEC
        for relative in (".ai", ".ai/ready-check", ".ai/ready-check/tmp"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory(dir=self.root) as temporary:
                root = Path(temporary)
                project, external, evidence = root / "project", root / "external", root / "evidence"
                for directory in (project, external, evidence):
                    directory.mkdir()
                link = project / relative
                link.parent.mkdir(parents=True, exist_ok=True)
                try:
                    link.symlink_to(external, target_is_directory=True)
                except OSError as error:
                    self.skipTest(f"Symlinks unavailable: {error}")
                check = Lint("debug", project, SimpleNamespace(name="ddev"), evidence, 60, {}, [], {}, None, SPEC)
                with self.assertRaisesRegex(ValueError, "real directories"):
                    check.run()
                self.assertFalse(list(external.iterdir()))

    def test_container_check_cleans_only_its_own_bridge(self):
        from types import SimpleNamespace
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
        sys.path.insert(0, str(PLUGIN / "profiles/drupal/scripts"))
        from core_checks import Lint
        from spec import SPEC
        active = self.project / ".ai/ready-check/tmp/.ready-check-lint.active"
        active.mkdir(parents=True)
        (active / "config.xml").write_bytes(b"Other active run")
        evidence = self.root / "evidence"
        evidence.mkdir()
        check = Lint("debug", self.project, SimpleNamespace(name="ddev"), evidence, 60, {}, [], {}, None, SPEC)
        self.assertEqual(check.run()["status"], "PASS")
        self.assertFalse(check.temp.exists())
        self.assertEqual(list(active.parent.iterdir()), [active])
        self.assertEqual((active / "config.xml").read_bytes(), b"Other active run")

    def test_linter_config_is_not_searched_outside_ancestors(self):
        self.managed_tools()
        self.write("web/modules/custom/other/eslint.config.js", "export default [];\n")
        self.git("add", "web/modules/custom/other/eslint.config.js")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "Config")
        self.write("web/modules/custom/demo/new.js", "const value = 1;\n")
        result = self.check("doctor")
        self.assertEqual(self.checker(result, "js")["status"], "READY", result)
        self.assertEqual(self.checker(result, "js")["tools"][0]["configuration"]["source"], "profile")

    def test_core_prefixes_are_excluded(self):
        self.git("checkout", "--", "web/modules/custom/demo/demo.php")
        paths = ("core/lib/Foo.php", "web/core/lib/Foo.php", "docroot/core/lib/Foo.php", "html/core/lib/Foo.php")
        for path in paths:
            self.write(path, "<?php\n")
        result = self.check()
        self.assertEqual(result["status"], "N/A", result)
        self.assertEqual(result["scope"]["excluded_files"], sorted(paths))

    def test_phpstan_config_discovery_is_deterministic_and_skips_core(self):
        self.managed_tools()
        (self.project / "phpstan.neon").unlink()
        self.write("core/phpstan.neon.dist", "parameters:\n  level: 0\n")
        self.write("vendor/mglaman/phpstan-drupal/extension.neon", "parameters: {}\n")
        result = self.check("doctor")
        self.assertEqual(self.checker(result, "phpstan")["tools"][0]["configuration"]["source"], "profile", result)
        self.write("web/phpstan.neon.dist", "parameters:\n  level: 0\n")
        result = self.check("doctor")
        self.assertEqual(self.checker(result, "phpstan")["tools"][0]["configuration"]["path"], "web/phpstan.neon.dist")

    def test_output_is_allowed_only_in_ready_check_data_inside_project(self):
        output = self.project / ".ai/ready-check/static.json"
        result = self.check(extra=("--output", str(output)))
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)
        self.assertTrue(Path(result["evidence_directory"]).is_relative_to(self.project / ".ai/ready-check/evidence"))
        for rejected in (".ai/other/static.json", "ai/ready-check/static.json", "reports/static.json"):
            self.assertEqual(self.check("doctor", extra=("--output", str(self.project / rejected)))["status"], "INCOMPLETE")
            self.assertFalse((self.project / rejected).exists())

    def test_doctor_has_no_stage_gate(self):
        result = self.check("doctor")
        self.assertEqual(result["status"], "READY")
        self.assertNotIn("can_proceed", result)

    def test_dump_call_is_a_debug_finding(self):
        self.write("web/modules/custom/demo/demo.php", "<?php\n\ndump($value);\n")
        self.assertEqual(self.checker(self.check(), "debug")["status"], "FAIL")
        self.write("web/modules/custom/demo/demo.php", "<?php\n\nxdump($value);\n")
        self.assertEqual(self.checker(self.check(), "debug")["status"], "PASS")


class EslintFatalTest(unittest.TestCase):
    def report(self, lines, messages):
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
        from core_checks import Lint, eslint_report

        lint = SimpleNamespace(lines=lines, findings=[], check="js", relative=lambda file: file)
        lint.add = lambda *args, **kwargs: Lint.add(lint, *args, **kwargs)
        eslint_report(lint, [dict(filePath="a.js", messages=messages)])
        return lint.findings

    def test_fatal_parse_error_ignores_the_changed_line_filter(self):
        fatal = dict(line=40, message="Parsing error", severity=2, ruleId=None, fatal=True)
        plain = dict(line=40, message="Unused", severity=2, ruleId="no-unused-vars")
        self.assertEqual([f["message"] for f in self.report({"a.js": {1}}, [fatal, plain])], ["Parsing error"])
        self.assertEqual(len(self.report({"b.js": None}, [fatal])), 0)
        self.assertEqual(len(self.report({"a.js": None}, [fatal, plain])), 2)



class StylelintSyntaxErrorTest(unittest.TestCase):
    def report(self, lines, warnings):
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
        from core_checks import Lint, stylelint_report

        lint = SimpleNamespace(lines=lines, findings=[], check="js", relative=lambda file: file)
        lint.add = lambda *args, **kwargs: Lint.add(lint, *args, **kwargs)
        stylelint_report(lint, [dict(source="a.css", warnings=warnings)])
        return lint.findings

    def test_css_syntax_error_ignores_the_changed_line_filter(self):
        syntax = dict(line=40, text="Unclosed block (CssSyntaxError)", severity="error", rule="CssSyntaxError")
        plain = dict(line=40, text="Unexpected", severity="error", rule="color-no-invalid-hex")
        self.assertEqual([f["message"] for f in self.report({"a.css": {1}}, [syntax, plain])], [syntax["text"]])
        self.assertEqual(len(self.report({"b.css": None}, [syntax])), 0)
        self.assertEqual(len(self.report({"a.css": None}, [syntax, plain])), 2)


class FormatterDiffLinesTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))

    def test_insertions_count_on_both_neighbours_and_replacements_do_not(self):
        from core_checks import changed_lines

        self.assertEqual(changed_lines("@@ -10,3 +10,4 @@\n a\n+b\n c\n"), [10, 11])
        self.assertEqual(changed_lines("@@ -5,0 +6,2 @@\n+x\n+y\n"), [5, 6])
        self.assertEqual(changed_lines("@@ -0,0 +1,2 @@\n+x\n+y\n"), [1])
        self.assertEqual(changed_lines("@@ -6,3 +6,2 @@\n-x=[1,\n-2]\n+x = [1, 2]\n y\n"), [6, 7])
        self.assertEqual(changed_lines("@@ -1,2 +1,2 @@\n-a\n+b\n c\n\\ No newline at end of file\n"), [1])

    def test_a_diff_without_numbered_hunks_is_reported_at_line_zero(self):
        from core_checks import format_line

        lint = SimpleNamespace(lines={"a.php": {7}}, relative=lambda name: name)
        self.assertEqual(format_line(lint, "a.php", "--- Original\n+++ New\n@@ @@\n-a\n+b\n"), 0)
        self.assertEqual(format_line(lint, "a.php", None), 0)
        self.assertIsNone(format_line(lint, "b.php", "@@ @@\n-a\n+b\n"))
        self.assertIsNone(format_line(lint, "a.php", "@@ -1,2 +1,2 @@\n-a\n+b\n"))


class GitWhitespaceCheckTest(unittest.TestCase):
    def run_check(self, stdout, lines):
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
        from core_checks import Lint

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        lint = SimpleNamespace(temp=Path(temporary.name), files=["a.txt"], merge="", lines={"a.txt": lines}, findings=[],
                               check="diff", relative=lambda file: file, call=lambda *args, **kwargs: (2, stdout, b""))
        lint.add = lambda *args, **kwargs: Lint.add(lint, *args, **kwargs)
        Lint.diff(lint)
        return [(f["line"], f["message"]) for f in lint.findings]

    def test_echoed_content_rows_are_not_parsed_as_findings(self):
        out = b"a.txt:2: trailing whitespace.\n+meeting at 10:30: standup  \n"
        self.assertEqual(self.run_check(out, None), [(2, "trailing whitespace.")])


if __name__ == "__main__":
    unittest.main()
