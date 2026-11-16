import json
import shutil
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from helpers import TempHome
from test_loading import install_fixtures
from test_profile import AXES
import digest
import profiles
import report
import sessions
import signals
import storage
from redact import redact
from sessions import Turn, clean_request
from sources import claude, codex

TODAY = date(2026, 11, 16)


class Home(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)
        install_fixtures(self.home)

    def write(self, relative, lines):
        path = self.home.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines))
        return path


class EmptyPreviousTest(Home):
    def test_empty_previous_period_is_not_charted(self):
        data = digest.build("month", TODAY)
        self.assertEqual(data["previous"]["summary"]["sessions"], 0)
        self.assertIsNone(data["previous"]["axes"])
        profiles.set_axes(AXES, "x", None)
        ids = [item["id"] for item in data["evidence"]]
        portrait = {"schema_version": 1, "summary": "s", "axes": [{"id": axis["id"], "score": 5, "reason": "r",
                    "evidence": ids[:1]} for axis in AXES], "strengths": [], "growth": [], "observations": [],
                    "themes": [], "archetype": None, "coverage": None}
        page = report.render_html(data, portrait, profiles.read(), None)
        self.assertNotIn("vs previous", page)
        self.assertNotIn("previous: 0", page)


class ProfileSafetyTest(Home):
    def test_corrupt_profile_is_not_overwritten(self):
        profiles.set_axes(AXES, "x", None)
        path = self.home.root / "data/profile.json"
        path.write_text('{"epochs": [')

        with self.assertRaises(ValueError):
            profiles.read()

        with self.assertRaises(ValueError):
            profiles.set_options(period="year")

        self.assertEqual(path.read_text(), '{"epochs": [')

    def test_write_is_atomic(self):
        target = self.home.root / "data/profile.json"
        storage.write_private(target, "old")

        def partial(path, text, **options):
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(text[:1])

            raise OSError("disk full")

        with mock.patch("pathlib.Path.write_text", partial):
            with self.assertRaises(OSError):
                storage.write_private(target, "new")

        self.assertEqual(target.read_text(), "old")


class ShapeTest(Home):
    def test_odd_records_are_skipped(self):
        path = self.write("claude/-p/odd.jsonl", [
            {"type": "user", "message": "hi"}, {"type": "assistant", "message": ["x"]}, {"type": "user", "cwd": 5},
            {"type": "user", "timestamp": "2026-11-10T09:00:00Z", "message": {"content": "real request here"}},
            {"type": "assistant", "message": {"content": "text", "usage": {"input_tokens": "lots"}}},
        ])
        session = claude.read(path)
        self.assertEqual([turn.request for turn in session.turns], ["real request here"])

    def test_codex_odd_payload_and_compaction(self):
        path = self.write("codex/x/odd.jsonl", [
            {"type": "event_msg", "payload": "oops"},
            {"timestamp": "2026-11-10T10:00:00Z", "type": "event_msg", "payload": {"type": "user_message", "message": "old style request"}},
            {"timestamp": "2026-11-10T10:00:01Z", "type": "event_msg", "payload": {"type": "item_completed",
             "item": {"type": "UserMessage", "content": [{"type": "text", "text": "old style request"}]}}},
            {"type": "response_item", "payload": {"type": "compaction"}},
        ])
        session = codex.read(path)
        self.assertEqual([turn.request for turn in session.turns], ["old style request"])
        self.assertEqual(session.compactions, 1)

    def test_one_failing_file_does_not_fail_load(self):
        original = claude.read

        def flaky(path):
            if path.name == "s1.jsonl":
                raise AttributeError("boom")

            return original(path)

        with mock.patch.object(claude, "read", side_effect=flaky):
            found, stats = sessions.load(None, TODAY)

        self.assertEqual(sorted(session.client for session in found), ["codex", "cursor"])
        self.assertEqual(stats[0]["failed_files"], 1)


class InjectedTest(unittest.TestCase):
    def test_more_injected_blocks(self):
        for text in ("<bash-input>ls</bash-input>", "<bash-stdout>files</bash-stdout><bash-stderr></bash-stderr>",
                     "<user-memory-input>remember x</user-memory-input>", "<turn_aborted>x</turn_aborted>",
                     "<user_shell_command>ls</user_shell_command>", "<skill>\n<name>x</name>\nbody</skill>"):
            self.assertEqual(clean_request(text), "", text)


class RedactionGapTest(unittest.TestCase):
    def test_more_secrets(self):
        for text in ('{"password": "hunter2"}', "DB_PASS=abc123", "pwd=abc123", "sk_live_abcdefghijklmnop1234",
                     "gho_abcdefghijklmnopqrstuvwx", "glpat-abcdefghijklmnopqrst", "AIzaSyA1234567890abcdefghijklmnop",
                     "npm_abcdefghijklmnopqrstuvwxyz0123", "hf_abcdefghijklmnopqrstuvwxyzAB"):
            result = redact(text)
            self.assertIn("<secret>", result, text)
            self.assertNotRegex(result, r"hunter2|abc123|abcdefghijklmnop", text)

    def test_windows_home(self):
        with mock.patch.object(Path, "home", return_value=Path("C:/Users/Jane")):
            self.assertEqual(redact(r"open c:\Users\jane\a.py and C:/Users/Jane/b.py"), r"open ~\a.py and ~/b.py")


class CacheRedactionTest(Home):
    def test_cache_holds_no_raw_secret(self):
        self.write("claude/-p/secret.jsonl", [
            {"type": "user", "timestamp": "2026-11-10T09:00:00Z",
             "message": {"content": "deploy with token ghp_abcdefghijklmnopqrstuvwxyz0123456789"}}])
        sessions.load(None, TODAY)
        text = "".join(path.read_text() for path in (self.home.root / "data/cache").rglob("*.json"))
        self.assertNotIn("ghp_abcdefghijklmnop", text)


class CyrillicTest(unittest.TestCase):
    def test_word_boundaries(self):
        self.assertEqual(signals.flags(Turn(None, "не тестуй поки"), []), [])
        self.assertEqual(signals.flags(Turn(None, "не только это"), []), [])
        self.assertEqual(signals.flags(Turn(None, "це не те, що треба"), []), ["correction"])


class ClaudeTokensTest(Home):
    def test_usage_counted_once_per_message(self):
        usage = {"input_tokens": 100, "output_tokens": 10}
        path = self.write("claude/-p/tokens.jsonl", [
            {"type": "user", "timestamp": "2026-11-10T09:00:00Z", "message": {"content": "do the thing please"}},
            {"type": "assistant", "message": {"id": "m1", "content": [{"type": "text", "text": "a"}], "usage": usage}},
            {"type": "assistant", "message": {"id": "m1", "content": [{"type": "tool_use", "name": "Read", "input": {}}], "usage": usage}},
            {"type": "assistant", "message": {"id": "m2", "content": [{"type": "text", "text": "b"}], "usage": usage}},
        ])
        self.assertEqual(claude.read(path).turns[0].tokens, 220)


if __name__ == "__main__":
    unittest.main()
