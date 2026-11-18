import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
import dependency_support
from process_support import execute, launch_argv, node_entry


class PlatformTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready check plateforme é ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def test_native_data_locations_and_explicit_override(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "Local Data"), "XDG_DATA_HOME": str(self.root / "xdg")}, clear=True):
            with patch.object(dependency_support.sys, "platform", "win32"):
                self.assertEqual(dependency_support.data_root(), (self.root / "Local Data/ReadyCheck").resolve())
            with patch.object(dependency_support.sys, "platform", "darwin"), patch.object(Path, "home", return_value=self.root):
                self.assertEqual(dependency_support.data_root(), (self.root / "Library/Application Support/ReadyCheck").resolve())
            with patch.object(dependency_support.sys, "platform", "linux"):
                self.assertEqual(dependency_support.data_root(), (self.root / "xdg/ready-check").resolve())
            with patch.dict(os.environ, READY_CHECK_DATA_DIR=str(self.root / "données partagées")):
                for platform in ("linux", "darwin", "win32"):
                    with patch.object(dependency_support.sys, "platform", platform):
                        self.assertEqual(dependency_support.data_root(), (self.root / "données partagées").resolve())

    def test_process_preserves_unicode_spaces_and_shell_metacharacters(self):
        arguments = ["mon fichier é", "a&b", "$(echo nope)", "semi;colon", 'a"b', "C:\\Users\\Some User\\file.php"]
        code, output, _ = execute([sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))", *arguments], self.root)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), arguments)
        self.assertFalse((self.root / "nope").exists())

    def test_explicit_data_dir_does_not_require_user_home(self):
        directory = self.root / "données partagées"
        with patch.dict(os.environ, {"READY_CHECK_DATA_DIR": str(directory)}, clear=True), \
                patch.object(Path, "home", side_effect=RuntimeError("No home directory")):
            self.assertEqual(dependency_support.data_root(), directory.resolve())

    def test_python_proxies_do_not_need_executable_mode_or_shebang_support(self):
        binary = self.write("vendor/bin/checker", '#!/usr/bin/env python3\nprint("portable")\n')
        code, output, _ = execute([str(binary)], self.root)
        self.assertEqual((code, output.strip()), (0, b"portable"))

    @unittest.skipIf(os.name == "nt" or any(c.isspace() for c in sys.executable), "Requires a POSIX shebang")
    def test_installed_python_command_keeps_its_interpreter_and_flags(self):
        binary = self.write("bin/yamllint", f"#!{sys.executable} -S\nimport sys\nprint(sys.flags.no_site)\n")
        binary.chmod(0o755)
        code, stdout, _ = execute([str(binary)], self.root)
        self.assertEqual((code, stdout.strip()), (0, b"1"))

    def test_relative_proxy_uses_command_working_directory(self):
        self.write("vendor/bin/checker", '#!/usr/bin/env python3\nprint("relative")\n')
        code, output, _ = execute(["vendor/bin/checker"], self.root)
        self.assertEqual((code, output.strip()), (0, b"relative"))

    def test_windows_npm_and_composer_launch_without_cmd_interpolation(self):
        npm = self.write("Node Folder/npm.cmd", "@echo off\n")
        entry = self.write("Node Folder/node_modules/npm/bin/npm-cli.js", "console.log('npm');\n")
        self.assertEqual(launch_argv([str(npm), "ci", "a&b"])[1:], [str(entry), "ci", "a&b"])
        composer = self.write("PHP Folder/composer.bat", "@echo off\n")
        phar = self.write("PHP Folder/composer.phar", "<?php echo 'composer';")
        self.assertEqual(launch_argv([str(composer), "install"])[1:], [str(phar), "install"])

    def test_windows_node_bin_wrapper_resolves_package_entry(self):
        binary = self.write("node_modules/.bin/eslint.cmd", "@echo off\n")
        self.write("node_modules/eslint/package.json", json.dumps({"bin": {"eslint": "bin/eslint.js"}}))
        entry = self.write("node_modules/eslint/bin/eslint.js", "console.log('eslint');")
        self.assertEqual(launch_argv([str(binary), "a&b"])[1:], [str(entry.resolve()), "a&b"])

    def test_node_entry_cannot_escape_package(self):
        self.write("node_modules/example/package.json", json.dumps({"bin": "../../outside.js"}))
        self.write("outside.js", "")
        with self.assertRaises(ValueError):
            node_entry(self.root, "example", "example")

    def test_timeout_terminates_process(self):
        with self.assertRaisesRegex(ValueError, "timed out"):
            execute([sys.executable, "-c", "import time; time.sleep(30)"], self.root, timeout=0.1)

    def test_native_entry_forwards_subcommand_help(self):
        process = subprocess.run([sys.executable, str(PLUGIN / "scripts/ready-check.py"), "setup", "--help"],
                                 capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--component", process.stdout)

    def test_windows_host_keeps_container_paths_posix(self):
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
        from core_runner import Runner
        with patch.dict(os.environ, {"LINT_RUNNER": "compose", "LINT_CONTAINER_ROOT": "/var/www/my site"}):
            runner = Runner(self.root, {}, dict(services=("php",), root="/var/www/html"))
            self.assertEqual(runner.path("vendor", "bin/phpcs"), "/var/www/my site/vendor/bin/phpcs")


if __name__ == "__main__":
    unittest.main()
