import io
import json
import shutil
import stat
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from helpers import TempHome
from test_loading import install_fixtures
import gnothi


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
