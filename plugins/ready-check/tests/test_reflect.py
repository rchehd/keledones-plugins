import json
import unittest
from os import utime
from pathlib import Path
from unittest.mock import patch

from helpers import RepoTest
import reflect_collect


STAGES = {"READY TO PUSH": ("--static", "PASS", "--review", "PASS", "--qa", "PASS"), "BLOCKED": ("--review", "FAIL")}


class ReflectTest(RepoTest):
    def task(self, title, rounds):
        target = self.entry_json("reports", "--project", str(self.repo), "--task", title)
        Path(target["report"]).write_text(f"task_id: {target['task_id']}\nRound: {len(rounds)}\nVerdict: x\n")

        for number, (verdict, extra) in enumerate(rounds, 1):
            self.entry_json("summary", "--project", str(self.repo), "--task", target["task_id"], "--round", str(number),
                            "--verdict", verdict, *STAGES[verdict], *extra)

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
        (branch_dir / "report.md").write_text("Вердикт **READY TO PUSH**\n", encoding="utf-8")
        digest = self.entry_json("reflect-collect", "--project", str(self.repo))
        task = digest["tasks"][0]
        self.assertEqual((task["verdict"], task["rounds"], digest["totals"]["without_summary"]), ("READY TO PUSH", None, 1))
        metrics = {item["label"]: item["value"] for item in reflect_collect.dashboard(digest, "en")["metrics"]}
        self.assertEqual(metrics["Passed in round 1"], "No data")
        self.assertEqual(metrics["Tasks with defects"], "No data")
        self.assertEqual(metrics["QA test problems"], "No data")
        with patch.object(reflect_collect, "chart_source", return_value=None):
            self.assertIn("<td>Passed in round 1</td><td>No data</td>", reflect_collect.render_html(digest))

    def test_offline_html_uses_localized_headings_and_verdicts(self):
        self.task("Localized", [("BLOCKED", [])])
        digest = reflect_collect.collect(self.repo, 10)
        with patch.object(reflect_collect, "chart_source", return_value=""):
            page = reflect_collect.render_html(digest, "uk")
        self.assertIn('<html lang="uk">', page)
        self.assertIn("<h1>Огляд задач</h1>", page)
        self.assertIn("<td>Є блокери</td>", page)
        self.assertNotIn("<td>BLOCKED</td>", page)
        with self.assertRaisesRegex(ValueError, "complete translation"):
            reflect_collect.render_html(digest, "pl-PL")

    def test_html_combines_historical_widget_and_confirmed_chat_decisions(self):
        task = self.task("Decisions", [("BLOCKED", []), ("READY TO PUSH", [])])
        directory = Path(self.entry_json("reports", "--project", str(self.repo), "--task", task)["directory"])
        summary_path = directory / "summary.json"
        original_rounds = json.loads(summary_path.read_text(encoding="utf-8"))["rounds"]
        legacy = dict(view="review", round=1, rows=[
            dict(id="F-001", action="false-positive", reason="Original explanation"),
            dict(id="F-004", action="accept-risk", reason="Kept from the old widget"),
        ])
        (directory / "ui-review-decision-fixture.json").write_text(json.dumps(legacy), encoding="utf-8")
        self.entry_json("summary", "--project", str(self.repo), "--task", task, "--round", "1",
                        "--disposition", "F-001:false-positive:Review:Initial chat triage")
        for _ in range(2):
            self.entry_json("summary", "--project", str(self.repo), "--task", task, "--round", "1",
                            "--disposition", "F-001:accept-risk:Review:An earlier risk explanation",
                            "--disposition", "F-001:false-positive:Review:An earlier classification",
                            "--disposition", "F-001:accept-risk:Review:Accepted: migration already planned",
                            "--disposition", "QA-002:false-positive:QA:Incorrect fixture")

        saved = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["rounds"], original_rounds)
        finding, = (row for row in saved["dispositions"] if row["id"] == "F-001")
        self.assertEqual(finding["action"], "accept-risk")
        digest = self.entry_json("reflect-collect", "--project", str(self.repo), "--html")
        self.assertEqual(digest["view_dispositions"], {"accept-risk": 2, "false-positive": 1})
        reasons = {row["id"]: row["reason"] for row in digest["tasks"][0]["view_feedback"]}
        self.assertEqual(reasons["F-001"], "Accepted: migration already planned")
        html = Path(digest["html"]).read_text(encoding="utf-8")
        self.assertIn("<td>Accepted risks</td><td>2</td>", html)
        self.assertIn("<td>False positives</td><td>1</td>", html)

    def test_legacy_dispositions_use_the_latest_revision_in_each_round(self):
        target = self.entry_json("reports", "--project", str(self.repo), "--task", "Legacy decisions")
        directory = Path(target["directory"])
        Path(target["report"]).write_text("Round: 2\nVerdict: READY TO PUSH\n", encoding="utf-8")
        older = [
            dict(id="F-001", action="false-positive", reason="Initial triage"),
            dict(id="F-002", action="accept-risk", reason="Initial risk"),
        ]
        current = [
            dict(id="F-001", action="accept-risk", reason="Updated risk"),
            dict(id="F-002", action="fix", reason="Selected for a fix"),
        ]
        reviews = (
            ("c", 1, 1, older, 1_700_000_003),
            ("a", 1, 2, current, 1_700_000_001),
            ("b", 2, 2, [older[0]], 1_700_000_002),
        )
        for name, round_number, revision, rows, modified in reviews:
            path = directory / f"ui-review-decision-{name}.json"
            path.write_text(json.dumps(dict(view="review", round=round_number, requirements_revision=revision,
                                            rows=rows)), encoding="utf-8")
            utime(path, (modified, modified))
        for name, reason, modified in (("b", "Old QA note", 1_700_000_001), ("a", "New QA note", 1_700_000_002)):
            path = directory / f"ui-qa-results-decision-{name}.json"
            path.write_text(json.dumps(dict(view="qa-results", round=2, action="false-positive",
                                            selected=["QA-001"], reason=reason)), encoding="utf-8")
            utime(path, (modified, modified))

        digest = self.entry_json("reflect-collect", "--project", str(self.repo))
        self.assertEqual(digest["view_dispositions"], {"accept-risk": 1, "false-positive": 2})
        decisions = {(row["round"], row["id"]): row["reason"] for row in digest["tasks"][0]["view_feedback"]}
        self.assertEqual(decisions, {(1, "F-001"): "Updated risk", (2, "F-001"): "Initial triage",
                                     (2, "QA-001"): "New QA note"})

    def test_chat_reclassification_removes_superseded_counts_in_that_round(self):
        task = self.task("Reclassified findings", [("BLOCKED", []), ("READY TO PUSH", [])])
        directory = Path(self.entry_json("reports", "--project", str(self.repo), "--task", task)["directory"])
        legacy = dict(view="review", round=1, rows=[
            dict(id="F-002", action="false-positive", reason="Initial widget triage"),
        ])
        (directory / "ui-review-decision-fixture.json").write_text(json.dumps(legacy), encoding="utf-8")
        command = ("summary", "--project", str(self.repo), "--task", task, "--round")
        for number in ("1", "2"):
            self.entry_json(*command, number, "--disposition", "F-001:accept-risk:Review:Initial risk")
        self.entry_json(*command, "1", "--disposition", "F-001:out-of-scope:Review:Scope clarified",
                        "--disposition", "F-002:fix:Review:User selected this finding for a fix")

        digest = self.entry_json("reflect-collect", "--project", str(self.repo), "--html")
        self.assertEqual(digest["view_dispositions"], {"accept-risk": 1})
        decision, = digest["tasks"][0]["view_feedback"]
        self.assertEqual((decision["round"], decision["id"], decision["action"]), (2, "F-001", "accept-risk"))
        html = Path(digest["html"]).read_text(encoding="utf-8")
        self.assertIn("<td>Accepted risks</td><td>1</td>", html)
        self.assertNotIn("<td>False positives</td>", html)

    def test_saved_overview_keeps_the_original_task_selection_and_coverage(self):
        first = self.task("First", [("READY TO PUSH", [])])
        legacy = self.entry_json("reports", "--project", str(self.repo), "--task", "Legacy")
        Path(legacy["report"]).write_text("Round: 1\nVerdict: READY TO PUSH\n", encoding="utf-8")
        earlier = self.entry_json("reflect-collect", "--project", str(self.repo), "--tasks", "2", "--html")
        before = Path(earlier["html"]).read_text(encoding="utf-8")
        self.task("New", [("BLOCKED", [])])
        later = self.entry_json("reflect-collect", "--project", str(self.repo), "--tasks", "1", "--html")
        self.assertNotEqual(earlier["html"], later["html"])
        self.assertEqual(Path(earlier["html"]).read_text(encoding="utf-8"), before)
        saved = reflect_collect.read_snapshot(self.repo, earlier["snapshot_id"])
        self.assertEqual({item["task_id"] for item in saved["tasks"]}, {first, legacy["task_id"]})
        self.assertNotIn("report", saved["tasks"][0])
        metrics = {item["label"]: item["value"] for item in reflect_collect.dashboard(saved, "en")["metrics"]}
        self.assertEqual(metrics["Passed in round 1"], "1 / 1")

    def test_feedback_reasons_are_scoped_to_selected_tasks(self):
        older = self.task("Older task", [("BLOCKED", [])])
        newer = self.task("Newer task", [("READY TO PUSH", [])])
        for task, reason in ((older, "Older fixture"), (newer, "Shared storage concurrency")):
            self.entry_json("feedback", "add", "--project", str(self.repo), "--task", task,
                            "--returned", "yes", "--reason", reason)
        data = self.entry_json("reflect-collect", "--project", str(self.repo), "--tasks", "1")
        self.assertEqual([item["task_id"] for item in data["tasks"]], [newer])
        self.assertEqual([(item["task"], item["reason"]) for item in data["feedback_reasons"]],
                         [(newer, "Shared storage concurrency")])
        self.assertEqual(data["totals"]["returned"], 1)

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
