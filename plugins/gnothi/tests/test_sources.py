import unittest
from datetime import datetime, timezone
from pathlib import Path

from helpers import fixture
import sessions
from sources import ADAPTERS, claude, codex, cursor


def kinds(turn):
    return [(action.kind, action.name) for action in turn.actions]


class SourcesTest(unittest.TestCase):
    def read(self, adapter, client):
        paths = list(adapter.files(fixture(client)))
        self.assertEqual(len(paths), 1)
        return adapter.read(paths[0])

    def test_adapters(self):
        self.assertEqual([adapter.CLIENT for adapter in ADAPTERS], ["claude", "codex", "cursor"])

    def test_claude(self):
        session = self.read(claude, "claude")
        self.assertEqual([turn.request for turn in session.turns],
                         ["Add a coupon field to the checkout form", "no, I meant the other file",
                          "Now run the linter on the checkout module"])
        self.assertEqual(kinds(session.turns[0]), [("skill", "superpowers:brainstorming"), ("test", ""), ("mcp", "context7")])
        self.assertEqual(kinds(session.turns[1]), [("subagent", "")])
        self.assertEqual([turn.outcome for turn in session.turns], ["completed", "interrupted", "completed"])
        self.assertEqual([turn.tokens for turn in session.turns], [140, None, None])
        self.assertEqual((session.project, session.client, session.skipped, session.compactions), ("shop", "claude", 1, 1))
        self.assertTrue(session.id.startswith("cc-"))
        self.assertEqual(session.started, datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(session.ended, datetime(2026, 11, 10, 9, 25, tzinfo=timezone.utc))

    def test_codex(self):
        session = self.read(codex, "codex")
        self.assertEqual([turn.request for turn in session.turns],
                         ["Add pagination to the users endpoint", "not that, I meant the admin endpoint",
                          "Explain why the cache is stale"])
        self.assertEqual(kinds(session.turns[0]), [("test", ""), ("mcp", "github")])
        self.assertEqual(kinds(session.turns[2]), [("plan", ""), ("skill", "review")])
        self.assertEqual([turn.outcome for turn in session.turns], ["completed", "interrupted", "completed"])
        self.assertEqual([turn.tokens for turn in session.turns], [500, 300, 200])
        self.assertEqual((session.project, session.skipped, session.compactions), ("api", 1, 1))
        self.assertTrue(session.id.startswith("cx-"))

    def test_cursor(self):
        session = self.read(cursor, "cursor")
        self.assertEqual([turn.request for turn in session.turns],
                         ["Write a post about caching", "no, I meant a shorter post", "Publish it to the drafts folder"])
        self.assertEqual(kinds(session.turns[0]), [("skill", "writer"), ("test", ""), ("mcp", "")])
        self.assertEqual([turn.outcome for turn in session.turns], ["completed", "interrupted", "completed"])
        self.assertEqual([turn.tokens for turn in session.turns], [None, None, None])
        self.assertEqual(session.turns[0].ts, datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc))
        self.assertEqual((session.project, session.skipped), ("blog", 1))
        self.assertTrue(session.id.startswith("cu-"))

    def test_cursor_without_timestamp_uses_file_date(self):
        path = Path(self.temporary_dir()) / "p/agent-transcripts/a/a.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text('{"role":"user","message":{"content":[{"type":"text","text":"hello there"}]}}\n')
        session = cursor.read(path)
        self.assertEqual(session.turns[0].ts.date(), datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date())

    def test_missing_root_yields_no_files(self):
        for adapter in ADAPTERS:
            self.assertEqual(list(adapter.files(Path("/nonexistent/gnothi"))), [])

    def test_root_from_environment(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"GNOTHI_CODEX_DIR": "/tmp/codex-here"}):
            self.assertEqual(codex.root(), Path("/tmp/codex-here"))

    def temporary_dir(self):
        import tempfile

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return temporary.name


class ClassifySkillFileTest(unittest.TestCase):
    def test_skill_file_read_counts_as_skill(self):
        self.assertEqual(sessions.classify("Read", "/x/skills/writer/SKILL.md"), sessions.Action("Read", "skill", "writer"))


if __name__ == "__main__":
    unittest.main()
