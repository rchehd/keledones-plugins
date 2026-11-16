import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parent.parent
SHARED = PLUGIN / "profiles/_shared"
sys.path.insert(0, str(SHARED / "core"))
sys.path.insert(0, str(PLUGIN / "scripts"))
import detect
from core_runner import Runner


class RecordingRunner(Runner):
    def __init__(self, project):
        with patch.dict(os.environ, {"LINT_RUNNER": "compose"}, clear=True):
            super().__init__(project, {}, dict(services=("php",), root="/app"))
        self.calls = []

    def exec(self, argv, timeout=15, input=None, env=None, cwd=None):
        self.calls.append((list(argv), input))
        return 0, b"", b""


class ContainerOperationsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-core.")
        self.addCleanup(temporary.cleanup)
        self.runner = RecordingRunner(Path(temporary.name))

    def last(self):
        return self.runner.calls[-1]

    def test_operations_use_posix_sh_without_php(self):
        runner = self.runner
        runner.write("/data/a b", b"\x00\xff", append=True)
        runner.write("/data/a b", b"x")
        runner.mkdir("/data/new", parents=True)
        runner.mkdir("/data/single")
        runner.unlink("/data/old")
        runner.rmdir("/data/dir")
        runner.replace("/data/tmp", "/data/final")
        runner.read("/data/file")
        runner.realpath("/data/x")
        runner.sh("true")
        self.assertEqual(len(runner.calls), 10)
        for argv, _ in runner.calls:
            self.assertEqual(argv[:2], ["sh", "-c"])
            self.assertNotIn("php", " ".join(argv))

    def test_write_passes_content_through_stdin_and_appends(self):
        self.runner.write("/data/a b", b"\x00\xff")
        argv, stdin = self.last()
        self.assertEqual((argv[2], argv[4:], stdin), ('cat > "$1"', ["/data/a b"], b"\x00\xff"))
        self.runner.write("/data/a b", b"more", append=True)
        argv, stdin = self.last()
        self.assertEqual((argv[2], stdin), ('cat >> "$1"', b"more"))

    def test_commands_are_shell_quoted_for_containers(self):
        self.runner.unlink("/data/a b; rm -rf /")
        argv, _ = self.last()
        self.assertEqual(shlex.split(shlex.join(argv))[-1], "/data/a b; rm -rf /")
        self.assertIn("'/data/a b; rm -rf /'", shlex.join(argv))

    def test_mkdir_unlink_rmdir_replace_commands(self):
        runner = self.runner
        runner.mkdir("/d", parents=True)
        self.assertIn("mkdir -p", self.last()[0][2])
        runner.mkdir("/d")
        self.assertNotIn("-p", self.last()[0][2])
        runner.unlink("/d")
        self.assertIn("rm -f", self.last()[0][2])
        runner.rmdir("/d")
        self.assertIn("rmdir", self.last()[0][2])
        runner.replace("/a", "/b")
        self.assertIn("mv -f", self.last()[0][2])
        self.assertEqual(self.last()[0][4:], ["/a", "/b"])

    def test_exists_uses_test_for_files_and_directories(self):
        commands = []
        self.runner.run = lambda command, *args, **kwargs: commands.append(command) or (0, b"", b"")
        self.assertTrue(self.runner.exists("/x y"))
        self.assertTrue(self.runner.exists("/x y", "dir"))
        self.assertEqual(commands, ["test -e '/x y' -o -L '/x y'", "test -d '/x y'"])

    def test_paths_with_control_characters_are_rejected(self):
        with patch.dict(os.environ, {"LINT_RUNNER": "compose", "LINT_CONTAINER_ROOT": "/app\nx"}, clear=True):
            with self.assertRaisesRegex(ValueError, "NUL or newline"):
                Runner(self.runner.project, {}, dict(services=("php",), root="/app"))


class LocalOperationsTest(unittest.TestCase):
    def test_local_branch_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="ready-check-core-local.") as folder:
            with patch.dict(os.environ, {"LINT_RUNNER": "local"}, clear=True):
                runner = Runner(Path(folder), {}, dict(services=("php",), root="/app"))
            target = str(Path(folder) / "a/b")
            runner.mkdir(target, parents=True)
            runner.write(target + "/f", b"one")
            runner.write(target + "/f", b"two", append=True)
            self.assertEqual(runner.read(target + "/f"), b"onetwo")
            runner.replace(target + "/f", target + "/g")
            self.assertFalse(runner.exists(target + "/f"))
            runner.unlink(target + "/g")
            runner.rmdir(target)
            self.assertFalse(runner.exists(target, "dir"))


class RunnerSelectionTest(unittest.TestCase):
    def test_every_detected_compose_file_is_used_by_the_runner(self):
        for name in detect.COMPOSE:
            with tempfile.TemporaryDirectory(prefix="ready-check-core-compose.") as folder:
                project = Path(folder)
                (project / name).write_text("services:\n  php:\n    image: y\n")
                with patch.dict(os.environ, {}, clear=True):
                    runner = Runner(project, {}, dict(services=("php",), root="/app"))
                self.assertEqual((detect.runner(project, project), runner.name, runner.compose), ("compose", "compose", name))

    def test_selection_order_is_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="ready-check-core-select.") as folder:
            project = Path(folder)
            (project / "compose.yaml").write_text("services:\n  web:\n    image: x\n  php:\n    image: y\n")
            defaults = dict(services=("missing", "php"), root="/app")
            with patch.dict(os.environ, {}, clear=True):
                runner = Runner(project, {}, defaults)
                self.assertEqual((runner.name, runner.service, runner.root), ("compose", "php", "/app"))
                self.assertEqual(Runner(project, {"service": "web", "container_root": "/srv"}, defaults).root, "/srv")
            with patch.dict(os.environ, {"LINT_SERVICE": "web", "LINT_RUNNER": "local"}, clear=True):
                runner = Runner(project, {"service": "php"}, defaults)
                self.assertEqual((runner.name, runner.service, runner.root), ("local", "web", str(project)))


class SharedFoldersTest(unittest.TestCase):
    def test_core_and_php_have_no_profile_names(self):
        for folder in ("core", "php"):
            files = sorted((SHARED / folder).glob("*.py"))
            self.assertTrue(files)
            for path in files:
                text = path.read_text(encoding="utf-8").lower()
                for word in ("drupal", "dpm", "kint", "laravel", "symfony"):
                    with self.subTest(file=path.name, word=word):
                        self.assertNotIn(word, text)

    def test_core_has_no_php_container_operations(self):
        for path in sorted((SHARED / "core").glob("*.py")):
            with self.subTest(file=path.name):
                self.assertNotIn("php -r", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
