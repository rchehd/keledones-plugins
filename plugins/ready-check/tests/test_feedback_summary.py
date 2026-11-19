import json
import unittest
from pathlib import Path

from helpers import RepoTest


class SummaryFeedbackTest(RepoTest):
    def new_task(self, title="Clear note"):
        return self.entry_json("reports", "--project", str(self.repo), "--task", title)

    def summary(self, task, round_number, verdict="BLOCKED", *extra, code=0):
        return self.entry_json("summary", "--project", str(self.repo), "--task", task, "--round", str(round_number),
                               "--verdict", verdict, "--static", "PASS", *extra, code=code)

    def test_rounds_are_appended_and_replaced(self):
        task = self.new_task()["task_id"]
        self.summary(task, 1, "BLOCKED", "--finding", "F-001:issue (blocking):review:I. Cache:RC-001:open")
        self.summary(task, 2, "READY TO PUSH", "--qa-case", "QA-001:PASS:2")
        self.summary(task, 2, "READY TO PUSH")
        data = json.loads(Path(self.new_task(task)["summary"]).read_text())
        self.assertEqual([entry["round"] for entry in data["rounds"]], [1, 2])
        self.assertEqual(data["rounds"][0]["findings"][0]["area"], "I. Cache")
        self.assertTrue(data["rounds"][1]["fingerprint"])

    def test_summary_needs_an_existing_task_and_a_known_verdict(self):
        self.assertIn("No report folder", self.summary("x-2026-11-10", 1, code=2)["reason"])
        process = self.run_entry("summary", "--project", str(self.repo), "--task", "x", "--round", "1", "--verdict", "DONE")
        self.assertEqual(process.returncode, 2)

    def test_feedback_uses_newest_task_and_last_round(self):
        task = self.new_task()["task_id"]
        self.summary(task, 1)
        self.summary(task, 2, "READY TO PUSH")
        record = self.entry_json("feedback", "add", "--project", str(self.repo), "--returned", "yes", "--by", "lead",
                                 "--reason", "anonymous cache", "--missed", "yes", "--area", "cache")["record"]
        self.assertEqual((record["task"], record["round"], record["missed"]), (task, 2, "yes"))

    def test_feedback_without_task_lists_tasks_and_accepts_other_branch(self):
        task = self.new_task()["task_id"]
        self.git("switch", "-q", "-c", "other")
        result = self.entry_json("feedback", "add", "--project", str(self.repo), "--returned", "yes", code=3)
        self.assertEqual(result["status"], "CHOOSE_TASK")
        self.assertEqual(result["tasks"][0]["task_id"], task)
        record = self.entry_json("feedback", "add", "--project", str(self.repo), "--task", task, "--returned", "yes")["record"]
        self.assertTrue(record["branch"].startswith("main-"))
        unknown = self.entry_json("feedback", "add", "--project", str(self.repo), "--task", "unknown", "--returned", "no")
        self.assertEqual(unknown["record"]["task"], "unknown")

    def test_feedback_list_skips_malformed_lines(self):
        self.new_task()
        self.entry_json("feedback", "add", "--project", str(self.repo), "--returned", "yes")
        with open(self.repo / ".ai/ready-check/feedback.jsonl", "a") as stream:
            stream.write("[1, 2]\nnot json\n")
        self.assertEqual(len(self.entry_json("feedback", "list", "--project", str(self.repo))["records"]), 1)


if __name__ == "__main__":
    unittest.main()
