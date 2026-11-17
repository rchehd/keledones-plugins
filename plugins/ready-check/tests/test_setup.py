import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


PLUGIN = Path(__file__).resolve().parent.parent
ENTRY = PLUGIN / "scripts/setup.py"


class SetupTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-setup-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "composer.json").write_text('{"require":{"drupal/core":"^10"}}\n')
        (self.project / "web/core/lib").mkdir(parents=True)
        (self.project / "web/core/lib/Drupal.php").write_text("<?php class Drupal { const VERSION = '10.6.0'; }\n")
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(("LINT_", "READY_CHECK_"))}
        self.env["LINT_RUNNER"] = "local"

    def run_setup(self, *args):
        process = subprocess.run([sys.executable, "-B", str(ENTRY), "--project", str(self.project),
                                  "--data-dir", str(self.root / "data"), *args],
                                 capture_output=True, text=True, encoding="utf-8", env=self.env)
        result = json.loads(process.stdout)
        self.assertEqual(process.returncode, 0 if result["status"] in {"PASS", "PLANNED"} else 2, process.stderr)
        return result

    def test_dry_run_does_not_create_installation_or_change_project(self):
        before = (self.project / "composer.json").read_bytes()
        result = self.run_setup("--dry-run")
        self.assertEqual(result["status"], "PLANNED", result)
        self.assertEqual(len(result["components"]), 2)
        self.assertFalse((self.root / "data").exists())
        self.assertEqual((self.project / "composer.json").read_bytes(), before)
        self.assertFalse((self.project / "vendor").exists())
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertFalse((self.project / "CLAUDE.local.md").exists())

    def test_dependency_directory_inside_project_is_rejected(self):
        result = self.run_setup("--data-dir", str(self.project / "tools"))
        self.assertEqual(result["status"], "INCOMPLETE", result)
        self.assertFalse((self.project / "tools").exists())

    def test_setup_previews_multiple_profiles_and_one_browser_bundle(self):
        (self.project / ".ready-check.json").write_text(json.dumps({"profiles": [
            dict(profile="drupal", application=".", runner="local"),
            dict(profile="generic", application=".", runner="local"),
        ]}))
        result = self.run_setup("--dry-run")
        self.assertEqual(result["status"], "PLANNED", result)
        self.assertEqual({part["component"] for part in result["components"]}, {"drupal", "generic", "browser"})
        self.assertEqual(len(result["components"]), 3)
        self.assertFalse((self.root / "data").exists())

    def test_unknown_profile_is_rejected_without_installing_browser(self):
        result = self.run_setup("--profile", "unknown")
        self.assertEqual(result["status"], "INCOMPLETE", result)
        self.assertFalse((self.root / "data").exists())

    @unittest.skipUnless(shutil.which("php"), "PHP is required")
    def test_runner_directory_inside_project_is_rejected(self):
        result = self.run_setup("--component", "profile", "--runner-data-dir", str(self.project / "tools"))
        self.assertEqual(result["status"], "INCOMPLETE", result)
        self.assertFalse((self.project / "tools").exists())

    def test_failed_browser_install_is_not_marked_ready(self):
        binaries = self.root / "bin"
        binaries.mkdir()
        for name, body in (("node", '#!/usr/bin/env python3\nprint("v20.19.0")\n'),
                           ("npm", '#!/usr/bin/env python3\nimport sys\nsys.exit(17)\n')):
            path = binaries / name
            path.write_text(body)
            path.chmod(0o755)
        self.env["PATH"] = str(binaries) + os.pathsep + self.env["PATH"]
        result = self.run_setup("--component", "browser")
        self.assertEqual(result["status"], "INCOMPLETE", result)
        self.assertFalse(list((self.root / "data").rglob("ready.json")))
        self.assertFalse(list((self.root / "data").rglob(".setup-lock")))
        self.assertFalse((self.project / "node_modules").exists())
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertFalse((self.project / "CLAUDE.local.md").exists())

    def test_version_parser_handles_node_v_prefix(self):
        spec = importlib.util.spec_from_file_location("ready_check_test_toolchain", PLUGIN / "profiles/_shared/core/core_toolchain.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Runner:
            def exec(self, command, timeout):
                return 0, b"v26.8.1\n", b""

        self.assertEqual(module.versioned(Runner(), "node", "node", "runner")["version"], "26.8.1")

    def test_new_ddev_install_uses_available_cache_parent(self):
        spec = importlib.util.spec_from_file_location("ready_check_test_ddev_data", PLUGIN / "profiles/_shared/core/core_toolchain.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Runner:
            name = "ddev"

            def sh(self, script, *args, **kwargs):
                if "-w" in script:
                    return b"1" if args == ("/mnt/ddev-global-cache",) else b"0"
                return b"/home/test/.local/share/ready-check"

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(module.runner_data_root(Runner()), "/mnt/ddev-global-cache/ready-check")
            self.assertEqual(module.runner_data_root(Runner(), "/custom/override"), "/custom/override")

    def test_unavailable_ddev_cache_uses_home_without_writing(self):
        spec = importlib.util.spec_from_file_location("ready_check_test_ddev_fallback", PLUGIN / "profiles/_shared/core/core_toolchain.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Runner:
            name = "ddev"

            def sh(self, script, *args, **kwargs):
                return b"0" if "-w" in script else b"/home/test/.local/share/ready-check"

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(module.runner_data_root(Runner()), "/home/test/.local/share/ready-check")

    def test_symlinked_data_path_cannot_write_into_project(self):
        try:
            (self.root / "data").symlink_to(self.project, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        result = self.run_setup("--component", "browser")
        self.assertEqual(result["status"], "INCOMPLETE", result)
        self.assertFalse((self.project / "browser").exists())

    def test_managed_compatibility_respects_installed_core_minimum(self):
        spec = importlib.util.spec_from_file_location("ready_check_test_compatibility", PLUGIN / "profiles/drupal/scripts/spec.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        core = self.project / "web/core/lib/Drupal.php"
        core.write_text("<?php class Drupal { const VERSION = '11.4.0'; const MINIMUM_PHP = '8.3.0'; }\n")

        class Runner:
            project = self.project

            def __init__(inner, version):
                inner.version = version

            def exec(inner, argv, timeout=15, input=None):
                return 0, inner.version.encode(), b""

        with self.assertRaises(ValueError):
            module.SPEC.compatibility(Runner("80200"))
        self.assertEqual(module.SPEC.compatibility(Runner("80300"))["drupal_major"], 11)
        core.write_text("<?php class Drupal { const VERSION = '11.4.0'; const MINIMUM_PHP = '8.4.0'; }\n")
        with self.assertRaises(ValueError):
            module.SPEC.compatibility(Runner("80300"))

    def test_missing_managed_browser_wrapper_never_installs(self):
        self.env["READY_CHECK_DATA_DIR"] = str(self.root / "data")
        result = subprocess.run([sys.executable, "-B", str(PLUGIN / "scripts/playwright.py"), "--version"],
                                env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 2)
        self.assertIn("ready:setup", result.stderr)
        self.assertFalse((self.root / "data").exists())

    def test_container_runners_forward_manifest_stdin(self):
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
        from core_runner import Runner
        binaries = self.root / "bin"
        binaries.mkdir()
        for name in ("ddev", "docker"):
            path = binaries / name
            path.write_text('#!/usr/bin/env python3\nimport shlex, subprocess, sys\nsys.exit(subprocess.run(shlex.split(sys.argv[-1])).returncode)\n')
            path.chmod(0o755)
        (self.project / "compose.yaml").write_text("services: {}\n")
        env = dict(self.env, PATH=str(binaries) + os.pathsep + self.env["PATH"], LINT_CONTAINER_ROOT="/var/www/html")
        for name in ("ddev", "compose"):
            with self.subTest(runner=name), patch.dict(os.environ, dict(env, LINT_RUNNER=name), clear=True):
                code, output, _ = Runner(self.project, {}, dict(services=("php",), root="/var/www/html")).run("cat", input=b"manifest-content")
                self.assertEqual(code, 0)
                self.assertEqual(output, b"manifest-content")


if __name__ == "__main__":
    unittest.main()
