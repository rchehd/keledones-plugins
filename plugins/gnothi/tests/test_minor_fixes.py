import json
import re
import sys
import unittest
from datetime import date

from helpers import TempHome
from test_loading import install_fixtures
from test_profile import AXES
import digest
import gnothi
import profiles
import report
import sessions
import storage
from redact import redact
from sources import claude, cursor

TODAY = date(2026, 11, 16)


class Home(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)
        install_fixtures(self.home)


class MetricsOnlyPrivacyTest(Home):
    def test_metrics_only_hides_roots_and_tool_names(self):
        plain = digest.build("all", TODAY)
        self.assertTrue(plain["tools"]["skills"])
        data = digest.build("all", TODAY, metrics_only=True)
        self.assertTrue(all("root" not in item for item in data["sources"]))
        self.assertTrue(all(re.fullmatch(r"skill-\d+", name) for name in data["tools"]["skills"]))
        self.assertTrue(all(re.fullmatch(r"mcp-\d+", name) for name in data["tools"]["mcp"]))
        self.assertEqual(sorted(data["tools"]["skills"].values()), sorted(plain["tools"]["skills"].values()))


class SchemelessUrlTest(unittest.TestCase):
    def test_hosts_without_scheme_are_masked(self):
        text = redact("see github.com/acme/private-repo, WWW.Example.org and api.acme.io:8080/v1, visit acme.com.")
        self.assertNotIn("acme", text)
        self.assertNotIn("Example", text)

    def test_file_names_stay(self):
        text = "edit signals.py, README.md, deploy.sh, script.pl, mymodule.info.yml, messages.es.json, self.app, user.email and ASP.NET notes"
        self.assertEqual(redact(text), text)


@unittest.skipIf(sys.platform == "win32", "POSIX permissions")
class IntermediateFoldersTest(Home):
    def test_created_parents_are_private(self):
        root = storage.data_root()
        storage.write_private(root / "cache/claude/x.json", "{}")

        for folder in (root, root / "cache", root / "cache/claude"):
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700, folder)


class PortraitShapeTest(Home):
    def test_odd_list_elements_are_reported_not_raised(self):
        data = digest.build("month", TODAY)
        portrait = {"schema_version": 1, "axes": [], "strengths": [{"title": "t", "detail": "d", "tip": "p",
                    "evidence": [["x"], 5]}], "growth": [], "themes": ["x", {"project": 1, "topics": "a"}],
                    "observations": [3], "archetype": None, "coverage": None}
        problems = report.validate(portrait, dict(data, metrics_only=True), profiles.read())
        self.assertTrue(any("evidence" in item for item in problems))
        self.assertTrue(any("themes" in item for item in problems))
        self.assertTrue(any("observations" in item for item in problems))


class AxisNameTest(unittest.TestCase):
    def test_non_string_name_is_a_validation_error(self):
        axes = [dict(axis) for axis in AXES]
        axes[0]["name"] = 5

        with self.assertRaises(ValueError):
            profiles.validate_axes(axes)


class AnchorTest(Home):
    def test_personal_and_universal_anchors_never_collide(self):
        axes = [dict(axis) for axis in AXES]
        axes[0]["id"] = "u-focus"
        profiles.set_axes(axes, "x", None)
        data = digest.build("month", TODAY)
        radar, _ = report.radar_data(data, {"axes": []}, profiles.read(), None)
        self.assertEqual(len(set(radar["anchors"])), len(radar["anchors"]))
        self.assertIn("axis-p-u-focus", radar["anchors"])


class PreviousEntryTest(Home):
    def history(self, *ends):
        lines = [json.dumps({"date": end, "period": "month", "epoch": 1, "start": None, "end": end, "axes": {"a": 1}})
                 for end in ends]
        storage.write_private(report.history_path(), "\n".join(lines) + "\n")

    def test_report_from_about_a_period_ago_is_compared(self):
        self.history("2026-10-18")
        self.assertEqual(report.previous_entry(digest.build("month", TODAY), 1)["end"], "2026-10-18")

    def test_mostly_overlapping_report_is_not_compared(self):
        self.history("2026-11-10")
        self.assertIsNone(report.previous_entry(digest.build("month", TODAY), 1))


class SkillEditTest(unittest.TestCase):
    def test_editing_a_skill_file_is_an_edit(self):
        self.assertEqual(sessions.classify("Edit", "/x/skills/review/SKILL.md").kind, "edit")
        self.assertEqual(sessions.classify("Read", "/x/skills/review/SKILL.md").kind, "skill")


class CachePruneTest(Home):
    def test_cache_drops_deleted_sessions(self):
        sessions.load(None, TODAY)
        cache = storage.data_root() / "cache/claude"
        before = len(list(cache.glob("*.json")))
        claude.files(claude.root())[0].unlink()
        sessions.load(None, TODAY)
        self.assertEqual(len(list(cache.glob("*.json"))), before - 1)


    def test_old_cache_is_rebuilt(self):
        path = claude.files(claude.root())[0]
        sessions.load(None, TODAY)
        target = sessions.cache_file(claude, path)
        data = json.loads(target.read_text())
        info = path.stat()
        data["key"], data["session"]["turns"][0]["request"] = [info.st_size, info.st_mtime_ns], "stale"
        target.write_text(json.dumps(data))
        self.assertNotEqual(sessions.cached(claude, path).turns[0].request, "stale")


class EmptyRootTest(Home):
    def test_empty_folder_is_not_found(self):
        empty = self.home.root / "empty"
        empty.mkdir()

        with unittest.mock.patch.dict("os.environ", {"GNOTHI_CODEX_DIR": str(empty)}):
            listed = {item["client"]: item["found"] for item in gnothi.sources(None)["sources"]}
            _, stats = sessions.load(None, TODAY)

        self.assertFalse(listed["codex"])
        self.assertFalse({item["client"]: item["found"] for item in stats}["codex"])


class CursorTimeTest(Home):
    def test_turn_without_timestamp_takes_previous_time(self):
        path = self.home.root / "cur/proj/agent-transcripts/a/a.jsonl"
        path.parent.mkdir(parents=True)
        first = "<timestamp>Monday, Nov 16, 2026, 10:00 AM (UTC+2)</timestamp>\n<user_query>first</user_query>"
        lines = [{"role": "user", "message": {"content": [{"type": "text", "text": first}]}},
                 {"role": "user", "message": {"content": [{"type": "text", "text": "<user_query>second</user_query>"}]}}]
        path.write_text("".join(json.dumps(line) + "\n" for line in lines))
        turns = cursor.read(path).turns
        self.assertEqual(turns[1].ts, turns[0].ts)


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
