import os
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import PLUGIN, TempHome
import storage


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)

    def test_default_root_per_platform(self):
        home = self.home.root / "user"
        env = {"LOCALAPPDATA": str(home / "Local"), "XDG_DATA_HOME": ""}

        with mock.patch.dict(os.environ, env), mock.patch.object(Path, "home", return_value=home):
            os.environ.pop("GNOTHI_DATA_DIR")

            with mock.patch.object(sys, "platform", "win32"):
                self.assertEqual(storage.data_root(), (home / "Local/Gnothi").resolve())

            with mock.patch.object(sys, "platform", "darwin"):
                self.assertEqual(storage.data_root(), (home / "Library/Application Support/Gnothi").resolve())

            with mock.patch.object(sys, "platform", "linux"):
                self.assertEqual(storage.data_root(), (home / ".local/share/gnothi").resolve())

    def test_env_override(self):
        self.assertEqual(storage.data_root(), self.home.root / "data")

    def test_refuses_git_tree(self):
        repository = self.home.root / "repo"
        (repository / ".git").mkdir(parents=True)

        with self.assertRaisesRegex(ValueError, "Git"):
            storage.write_private(repository / "deep/report.html", "x")

        self.assertFalse((repository / "deep").exists())

    def test_refuses_plugin_package(self):
        with self.assertRaises(ValueError):
            storage.guard(PLUGIN / "reports")

    def test_refuses_home(self):
        with mock.patch.object(Path, "home", return_value=self.home.root):
            with self.assertRaises(ValueError):
                storage.guard(self.home.root)

    @unittest.skipIf(sys.platform == "win32", "POSIX permissions")
    def test_permissions(self):
        path = storage.write_private(storage.data_root() / "reports/a.html", "x")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_forget_removes_known_layout(self):
        storage.write_private(storage.data_root() / "profile.json", "{}")
        storage.write_private(storage.data_root() / "cache/claude/a.json", "{}")
        storage.forget()
        self.assertFalse(storage.data_root().exists())

    def test_forget_refuses_unknown_entries(self):
        storage.write_private(storage.data_root() / "profile.json", "{}")
        notes = storage.data_root() / "notes.txt"
        notes.write_text("keep")

        with self.assertRaises(ValueError):
            storage.forget()

        self.assertTrue(notes.exists())


if __name__ == "__main__":
    unittest.main()
