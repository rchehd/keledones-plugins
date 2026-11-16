import json
import os
import shutil
import time
import tracemalloc
import unittest
from datetime import date
from unittest import mock

from helpers import TempHome, fixture
import sessions
from sources import claude, cursor


def install_fixtures(home):
    for client in ("claude", "codex", "cursor"):
        shutil.copytree(fixture(client), home.root / client)


class LoadingTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)
        install_fixtures(self.home)

    def test_filters_by_period(self):
        found, stats = sessions.load(date(2026, 11, 1), date(2026, 11, 16))
        self.assertEqual(sorted(session.client for session in found), ["claude", "codex", "cursor"])
        self.assertEqual([(item["client"], item["found"], item["files"], item["sessions"], item["skipped_lines"])
                          for item in stats],
                         [("claude", True, 1, 1, 1), ("codex", True, 1, 1, 1), ("cursor", True, 1, 1, 1)])
        self.assertEqual(sessions.load(date(2026, 11, 11), date(2026, 11, 16))[0], [])
        self.assertEqual(len(sessions.load(None, date(2026, 11, 16))[0]), 3)

    def test_second_load_uses_cache(self):
        with mock.patch.object(claude, "read", wraps=claude.read) as read:
            sessions.load(None, date(2026, 11, 16))
            sessions.load(None, date(2026, 11, 16))

        self.assertEqual(read.call_count, 1)
        cached = list((self.home.root / "data/cache/claude").glob("*.json"))
        self.assertEqual(len(cached), 1)
        self.assertIn("session", json.loads(cached[0].read_text()))

    def test_changed_file_is_reparsed(self):
        sessions.load(None, date(2026, 11, 16))
        path = cursor.files(cursor.root())[0]

        with open(path, "a", encoding="utf-8") as stream:
            stream.write('{"role":"user","message":{"content":[{"type":"text","text":"<timestamp>Tuesday, Nov 10, 2026, '
                         '9:30 AM (UTC+1)</timestamp><user_query>one more thing</user_query>"}]}}\n')

        os.utime(path, ns=(time.time_ns(), time.time_ns() + 10_000_000))
        found = sessions.load(None, date(2026, 11, 16))[0]
        self.assertEqual(len(next(session for session in found if session.client == "cursor").turns), 4)

    def test_reads_lines_lazily(self):
        path = self.home.root / "claude/-big/big.jsonl"
        path.parent.mkdir(parents=True)
        text = "x" * 1000
        line = json.dumps({"type": "assistant", "timestamp": "2026-11-10T09:00:00Z",
                           "message": {"content": [{"type": "text", "text": text}]}})

        with open(path, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"type": "user", "timestamp": "2026-11-10T09:00:00Z",
                                     "message": {"content": "start"}}) + "\n")

            for _ in range(50000):
                stream.write(line + "\n")

        tracemalloc.start()
        claude.read(path)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        self.assertLess(peak, 20 * 1024 * 1024)

    def test_missing_root_is_reported(self):
        shutil.rmtree(self.home.root / "codex")
        found, stats = sessions.load(None, date(2026, 11, 16))
        self.assertEqual(len(found), 2)
        self.assertEqual(stats[1]["found"], False)


if __name__ == "__main__":
    unittest.main()
