import io
import json
import shutil
import stat
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import TempHome
from test_loading import install_fixtures
import gnothi
import storage


def run(*args):
    stream = io.StringIO()

    with redirect_stdout(stream):
        code = gnothi.main(list(args))

    return code, json.loads(stream.getvalue())


class CliTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)
        install_fixtures(self.home)

    def test_sources_reports_missing_root(self):
        shutil.rmtree(self.home.root / "codex")
        code, result = run("sources")
        self.assertEqual((code, result["status"], result["action"]), (0, "PASS", "sources"))
        self.assertEqual([(item["client"], item["found"], item["files"]) for item in result["sources"]],
                         [("claude", True, 1), ("codex", False, 0), ("cursor", True, 1)])

    def test_collect_writes_digest(self):
        with mock.patch("digest.date") as clock:
            clock.today.return_value = gnothi.date(2026, 11, 16)
            code, result = run("collect", "--period", "month")

        self.assertEqual((code, result["status"]), (0, "PASS"))
        path = self.home.root / "data/tmp/digest.json"
        self.assertEqual(json.loads(path.read_text())["current"]["summary"]["sessions"], 3)
        self.assertEqual(result["digest"], str(path))

        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_storage_check_prepares_tmp_without_saving_data(self):
        code, result = run("storage-check")
        root = storage.data_root()
        self.assertEqual((code, result["status"], result["data_root"]), (0, "PASS", str(root)))
        self.assertEqual(list(root.iterdir()), [root / "tmp"])
        self.assertEqual(list((root / "tmp").iterdir()), [])

    def test_storage_check_reports_access_denied(self):
        with mock.patch("storage.os.replace", side_effect=PermissionError("[WinError 5] Access is denied")):
            code, result = run("storage-check")

        self.assertEqual((code, result["status"], result["error_code"]), (2, "FAIL", "storage_access_denied"))
        self.assertEqual(Path(result["path"]), storage.data_root())
        self.assertIn("WinError 5", result["reason"])
        self.assertEqual(list(storage.data_root().iterdir()), [])

    def test_collect_keeps_sessions_when_cache_cannot_be_written(self):
        replace = storage.os.replace
        cache = storage.data_root() / "cache"

        def blocked_cache(source, target):
            if cache in target.parents:
                raise PermissionError("Access is denied")
            return replace(source, target)

        with mock.patch("storage.os.replace", side_effect=blocked_cache):
            code, result = run("collect", "--period", "all")

        self.assertEqual((code, result["status"], result["current"]["summary"]["sessions"]), (0, "PASS", 3))
        self.assertTrue(all(item["failed_files"] == 0 for item in result["sources"]))

    def test_collect_no_save_reads_sessions_without_writing(self):
        with mock.patch("storage.write_private", side_effect=PermissionError("Access is denied")) as write:
            code, result = run("collect", "--period", "all", "--no-save")

        self.assertEqual((code, result["status"], result["current"]["summary"]["sessions"]), (0, "PASS", 3))
        self.assertNotIn("digest", result)
        self.assertFalse(storage.data_root().exists())
        write.assert_not_called()

    def test_collect_no_save_defaults_to_metrics_only_if_profile_is_unreadable(self):
        target = storage.data_root() / "profile.json"
        read_text = Path.read_text

        def blocked_profile(path, *args, **kwargs):
            if path == target:
                raise PermissionError("Access is denied")
            return read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", blocked_profile):
            code, result = run("collect", "--period", "all", "--no-save")

        self.assertEqual((code, result["status"], result["current"]["summary"]["sessions"]), (0, "PASS", 3))
        self.assertTrue(result["metrics_only"])
        self.assertEqual(result["evidence"], [])

    def test_bad_period_fails(self):
        with self.assertRaises(SystemExit):
            run("collect", "--period", "week")

    def test_forget_needs_yes(self):
        run("collect", "--period", "all")
        code, result = run("forget")
        self.assertEqual((code, result["status"]), (2, "FAIL"))
        self.assertTrue((self.home.root / "data").exists())
        code, result = run("forget", "--yes")
        self.assertEqual((code, result["status"]), (0, "PASS"))
        self.assertFalse((self.home.root / "data").exists())


if __name__ == "__main__":
    unittest.main()
