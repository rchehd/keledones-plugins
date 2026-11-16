import json
import unittest
from datetime import datetime, timedelta

import tasks
from helpers import RepoTest


class TaskRecordTest(RepoTest):
    def lines(self):
        return [json.loads(line) for path in sorted((self.repo / "ai/ready-check/tasks").glob("*/*.jsonl"))
                for line in path.read_text(encoding="utf-8").splitlines()]

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

    def test_task_folder_is_git_excluded(self):
        tasks.record(self.repo, "claude", "s", "task")
        self.assertEqual(self.git("status", "--short").strip(), "")

    def test_prune_removes_files_older_than_retention(self):
        tasks.record(self.repo, "claude", "s", "old", now=datetime.now() - timedelta(days=40))
        tasks.record(self.repo, "claude", "s", "new")
        self.assertEqual(tasks.prune(self.repo), 1)
        self.assertEqual([line["prompt"] for line in self.lines()], ["new"])

    def test_cli_groups_sessions_newest_first(self):
        tasks.record(self.repo, "claude", "a", "first")
        tasks.record(self.repo, "claude", "b", "second")
        result = self.entry_json("tasks", "--project", str(self.repo))
        self.assertEqual([session["session"] for session in result["sessions"]], ["b", "a"])


if __name__ == "__main__":
    unittest.main()
