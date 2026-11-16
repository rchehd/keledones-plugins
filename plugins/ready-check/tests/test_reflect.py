import json
import unittest
from pathlib import Path
from unittest.mock import patch

import reflect_collect
from helpers import RepoTest


class ReflectTest(RepoTest):
    def task(self, title, rounds):
        target = self.entry_json("reports", "--project", str(self.repo), "--task", title)
        Path(target["report"]).write_text(f"task_id: {target['task_id']}\nRound: {len(rounds)}\nVerdict: x\n")

        for number, (verdict, extra) in enumerate(rounds, 1):
            self.entry_json("summary", "--project", str(self.repo), "--task", target["task_id"], "--round", str(number),
                            "--verdict", verdict, *extra)

        return target["task_id"]

    def test_totals_join_summaries_and_feedback(self):
        first = self.task("First", [("READY TO PUSH", [])])
        second = self.task("Second", [("BLOCKED", ["--finding", "F-1:issue (blocking):review:Cache:RC-1:open",
                                                    "--qa-case", "QA-1:FAIL:1", "--qa-case", "QA-1:PASS:2"]),
                                      ("READY TO PUSH", [])])
        self.entry_json("feedback", "add", "--project", str(self.repo), "--task", second, "--returned", "yes",
                        "--missed", "yes", "--reason", "anonymous cache")
        digest = self.entry_json("reflect-collect", "--project", str(self.repo))
        totals = digest["totals"]
        self.assertEqual((totals["tasks"], totals["passed_first_round"], totals["with_defects"]), (2, 1, 1))
        self.assertEqual((totals["returned"], totals["returned_missed"], totals["qa_test_problems"]), (1, 1, 1))
        self.assertEqual(digest["areas"], [["Cache", 1]])
        self.assertEqual({task["task_id"] for task in digest["tasks"]}, {first, second})

    def test_legacy_report_without_summary_is_unknown(self):
        branch_dir = Path(self.entry_json("reports", "--project", str(self.repo), "--task", "Seed")["directory"]).parent
        for child in branch_dir.iterdir():
            child.rmdir()
        (branch_dir / "report.md").write_text("Вердикт **READY TO PUSH**\n")
        digest = self.entry_json("reflect-collect", "--project", str(self.repo))
        task = digest["tasks"][0]
        self.assertEqual((task["verdict"], task["rounds"], digest["totals"]["without_summary"]), ("READY TO PUSH", None, 1))

    def test_html_escapes_untrusted_text(self):
        bad = "</script><script>alert(1)</script>"
        task = self.task("Bad", [("BLOCKED", ["--finding", f"F-1:issue (blocking):review:{bad}:RC-1:open"])])
        self.entry_json("feedback", "add", "--project", str(self.repo), "--task", task, "--returned", "yes",
                        "--reason", "<img src=x onerror=alert(1)>")
        digest = reflect_collect.collect(self.repo, 10)

        with patch.object(reflect_collect, "chart_source", return_value="/* chart */"):
            page = reflect_collect.render_html(digest)

        self.assertNotIn(bad, page)
        self.assertNotIn("<img src=x", page)
        self.assertIn("new Chart", page)

        with patch.object(reflect_collect, "chart_source", return_value=None):
            page = reflect_collect.render_html(digest)

        self.assertNotIn("<script", page)
        self.assertIn("<table>", page)


if __name__ == "__main__":
    unittest.main()
