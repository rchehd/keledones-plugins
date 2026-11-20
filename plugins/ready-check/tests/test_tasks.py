import json
import os
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from helpers import RepoTest
import hook_state
import tasks


class TaskRecordTest(RepoTest):
    def lines(self):
        return [json.loads(line) for path in sorted((self.repo / ".ai/ready-check/tasks").glob("*/*.jsonl"))
                for line in path.read_text(encoding="utf-8").split("\n") if line]

    def test_long_prompt_is_cut_on_a_character_boundary(self):
        tasks.record(self.repo, "claude", "s", "ж" * 50000)
        prompt = self.lines()[0]["prompt"]
        self.assertLessEqual(len(prompt.encode("utf-8")), tasks.MAX_PROMPT)
        self.assertTrue(prompt and set(prompt) == {"ж"})

    def test_commands_and_blank_prompts_are_skipped(self):
        for prompt in ("/ready:check", " $check ", "/qa", "   ", None):
            self.assertIsNone(tasks.record(self.repo, "codex", "s", prompt))
        self.assertIsNotNone(tasks.record(self.repo, "codex", "s", "/ready:check the last commit against TASK.md"))

    def test_codex_question_reply_becomes_question_and_answer(self):
        reply = ('<send_user_message_question_reply>\n[{"questionItemId":"x","question":"Run Ready Check?",'
                 '"answer":"Yes, all checks"}]\n</send_user_message_question_reply>')
        tasks.record(self.repo, "codex", "s", reply)
        self.assertEqual(self.lines()[0]["prompt"], "Q: Run Ready Check?\nA: Yes, all checks")
        self.assertEqual(tasks.normalize("<send_user_message_question_reply>bad</send_user_message_question_reply>"),
                         "<send_user_message_question_reply>bad</send_user_message_question_reply>")

    def test_codex_reply_ignores_non_string_question_and_answer(self):
        reply = ('<send_user_message_question_reply>[{"question":null,"answer":"No"},'
                 '{"question":"Ok?","answer":null},{"question":5,"answer":["x"]},"junk"]'
                 '</send_user_message_question_reply>')
        self.assertEqual(tasks.normalize(reply), "Q: \nA: No\nQ: Ok?\nA: \nQ: \nA:")

    def test_branch_slug_is_stable_when_a_tag_shares_the_branch_name(self):
        self.git("checkout", "-q", "-b", "foo")
        self.git("tag", "foo")
        self.assertEqual(tasks.branch_name(self.repo), "foo")

    def test_records_keep_the_branch_during_a_rebase(self):
        self.git("checkout", "-q", "-b", "feature/x")
        self.git("commit", "-q", "--allow-empty", "-m", "two")
        sha = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-q", "--detach", sha)
        self.assertTrue(tasks.branch_name(self.repo).startswith("detached-"))
        git_dir = Path(self.git("rev-parse", "--absolute-git-dir").strip()) / "rebase-merge"
        git_dir.mkdir()
        (git_dir / "head-name").write_text("refs/heads/feature/x\n")
        self.assertEqual(tasks.branch_name(self.repo), "feature/x")

    def test_task_folder_is_git_excluded(self):
        tasks.record(self.repo, "claude", "s", "task")
        self.assertEqual(self.git("status", "--short").strip(), "")

    def test_prune_removes_files_older_than_retention(self):
        tasks.record(self.repo, "claude", "s", "old", now=datetime.now() - timedelta(days=40))
        tasks.record(self.repo, "claude", "s", "new")
        self.assertEqual(tasks.prune(self.repo), 1)
        self.assertEqual([line["prompt"] for line in self.lines()], ["new"])

    def test_unicode_line_separators_do_not_split_records(self):
        prompt = "first\u2028second\u2029third\x85end"
        tasks.record(self.repo, "claude", "s", prompt)
        self.assertEqual([line["prompt"] for line in tasks.recent(self.repo)], [prompt])
        tasks.record(self.repo, "claude", "s", "Q: " + prompt)
        tasks.record(self.repo, "claude", "s", "Q: " + prompt)
        self.assertEqual(len(self.lines()), 2)

    def test_prune_skips_files_that_vanish_during_the_scan(self):
        tasks.record(self.repo, "claude", "s", "old", now=datetime.now() - timedelta(days=40))
        original = Path.is_file

        def vanishing(path):
            if path.suffix == ".jsonl":
                raise FileNotFoundError(path)
            return original(path)

        with patch.object(Path, "is_file", vanishing):
            self.assertEqual(tasks.prune(self.repo), 0)

    def test_state_prune_tolerates_concurrent_removal(self):
        folder = self.data / "state"
        folder.mkdir(parents=True)
        stale = folder / "a.json"
        kept = folder / "b.json"
        stale.write_text("{}")
        kept.write_text("{}")
        old = time.time() - 30 * 86400
        os.utime(stale, (old, old))
        os.utime(kept, (old, old))

        def vanishing(path):
            path.unlink()
            return True

        with patch.object(Path, "is_file", vanishing):
            self.assertEqual(hook_state.prune(), 0)
        self.assertFalse(stale.exists())

    def test_cli_groups_sessions_newest_first(self):
        tasks.record(self.repo, "claude", "a", "first")
        tasks.record(self.repo, "claude", "b", "second")
        result = self.entry_json("tasks", "--project", str(self.repo))
        self.assertEqual([session["session"] for session in result["sessions"]], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
