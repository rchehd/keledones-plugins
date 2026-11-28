import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from helpers import RepoTest

import tasks


class QAGateTest(RepoTest):
    def setUp(self):
        super().setUp()
        self.gate_dir = self.root
        self.plan = {
            "schema_version": 1,
            "requirements": ["RC-001", "RC-002", "RC-003"],
            "scenarios": [
                {"id": "QA-001", "kind": "api", "required": True, "requirements": ["RC-001"]},
                {"id": "QA-002", "kind": "cli", "required": True, "requirements": ["RC-002"]},
                {"id": "QA-003", "kind": "ci", "required": True, "requirements": ["RC-003"]},
            ],
            "results": [
                {"id": "QA-001", "status": "PASS", "evidence": "evidence/QA-001-api.json"},
                {"id": "QA-002", "status": "PASS", "evidence": "evidence/QA-002-cli.txt"},
                {"id": "QA-003", "status": "PASS", "evidence": "evidence/QA-003-ci.json"},
            ],
        }
        self.evidence("evidence/QA-001-api.json", "evidence/QA-002-cli.txt", "evidence/QA-003-ci.json")

    def evidence(self, *paths):
        for name in paths:
            path = self.gate_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("evidence\n", encoding="utf-8")

    def stamp(self, name, moment):
        stamp = moment.timestamp()
        os.utime(self.gate_dir / name, (stamp, stamp))

    def gate(self, code):
        path = self.gate_dir / "qa-gate-input.json"
        path.write_text(json.dumps(self.plan), encoding="utf-8")
        return self.entry_json("qa-gate", "--input", str(path), code=code)

    def recorded_plan(self, round_number=1):
        report = self.entry_json("reports", "--project", str(self.repo), "--task", "Recording gate")
        Path(report["report"]).write_text("# QA\n", encoding="utf-8")
        self.gate_dir = Path(report["directory"])
        self.evidence("evidence/QA-002-cli.txt", "evidence/QA-003-ci.json")
        self.task = report["task_id"]
        self.plan["round"] = round_number
        self.plan["scenarios"][0].update(kind="browser", recording_required=True)
        self.plan["results"][0].update(attempt=1, evidence=f"evidence/round-{round_number}/QA-001-steps.md")

    def prepare_clip(self, case="QA-001", round_number=1, attempt=1):
        args = ("--project", str(self.repo), "--task", self.task, "--round", str(round_number),
                "--case", case, "--attempt", str(attempt))
        self.entry_json("qa-record", *args, "--action", "Click save", "--observed", "Observed the result")
        clip = self.entry_json("qa-record", *args, "--prepare-video", f"{case}-attempt-{attempt}.webm")
        return clip, (*args, "--finish-video", clip["video"])

    def record_clip(self, case="QA-001", round_number=1, attempt=1, outcome="PASS"):
        clip, finish = self.prepare_clip(case, round_number, attempt)
        Path(clip["path"]).write_bytes(clip["evidence"].encode())
        self.entry_json("qa-record", *finish, "--outcome", outcome)
        return clip["evidence"]

    def test_non_browser_cases_can_pass(self):
        result = self.gate(0)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["can_proceed"])
        self.assertEqual([case["kind"] for case in result["scenarios"]], ["api", "cli", "ci"])

    def test_failed_required_case_still_blocks_when_other_evidence_is_missing(self):
        self.plan["results"][1]["status"] = "FAIL"
        self.plan["results"].pop()
        result = self.gate(1)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failed_required"], ["QA-002"])
        self.assertEqual(result["pending_required"], ["QA-003"])
        self.assertFalse(result["can_proceed"])

    def test_required_prerequisite_and_result_absences_are_incomplete(self):
        self.plan["results"][0] = {"id": "QA-001", "status": "INCOMPLETE", "reason": "Test API is unavailable"}
        self.plan["results"].pop()
        result = self.gate(2)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["pending_required"], ["QA-001", "QA-003"])
        self.assertEqual(result["uncovered_requirements"], ["RC-001", "RC-003"])

    def test_inapplicable_case_needs_other_current_coverage(self):
        self.plan["results"][0] = {"id": "QA-001", "status": "N/A", "reason": "Only the contract changed"}
        self.assertEqual(self.gate(2)["uncovered_requirements"], ["RC-001"])
        self.plan["verified_requirements"] = {"RC-001": "evidence/current-contract-comparison.txt"}
        self.assertEqual(self.gate(0)["uncovered_requirements"], [])

    def test_mixed_case_plan_rejects_pass_without_evidence(self):
        self.plan["scenarios"].append({"id": "QA-004", "kind": "browser", "required": False, "requirements": []})
        self.plan["results"].append({"id": "QA-004", "status": "PASS"})
        result = self.gate(2)
        self.assertIn("QA-004 needs an evidence reference", result["reason"])
        self.plan["results"][-1]["evidence"] = "evidence/QA-004-browser.png"
        self.evidence("evidence/QA-004-browser.png")
        self.assertEqual(self.gate(0)["scenarios"][-1]["kind"], "browser")

    def test_native_mobile_case_needs_a_device_result(self):
        self.plan["scenarios"][0]["kind"] = "mobile"
        self.plan["results"][0] = {"id": "QA-001", "status": "INCOMPLETE", "reason": "Test device unavailable"}
        self.assertEqual(self.gate(2)["pending_required"], ["QA-001"])
        self.plan["results"][0] = {"id": "QA-001", "status": "PASS", "evidence": "evidence/QA-001-maestro.xml"}
        self.evidence("evidence/QA-001-maestro.xml")
        self.assertEqual(self.gate(0)["scenarios"][0]["kind"], "mobile")

    def test_desktop_case_uses_journal_and_actual_state_evidence(self):
        self.plan["scenarios"][0]["kind"] = "desktop"
        self.plan["results"][0]["evidence"] = ["evidence/QA-001-steps.md", "evidence/QA-001-window.png"]
        self.evidence(*self.plan["results"][0]["evidence"])
        self.assertEqual(self.gate(0)["scenarios"][0]["kind"], "desktop")

    def test_required_recording_must_reference_a_completed_unmodified_clip(self):
        self.recorded_plan()
        result = self.gate(2)
        self.assertEqual(result["pending_required"], ["QA-001"])
        self.assertEqual(result["missing_required_recordings"], ["QA-001"])
        self.assertEqual(result["scenarios"][0]["status"], "INCOMPLETE")
        self.assertEqual(result["uncovered_requirements"], ["RC-001"])

        clip, finish = self.prepare_clip()
        path = Path(clip["path"])
        self.plan["results"][0]["recording"] = clip["evidence"]
        self.assertEqual(self.gate(2)["missing_required_recordings"], ["QA-001"])
        path.touch()
        self.assertEqual(self.gate(2)["missing_required_recordings"], ["QA-001"])
        path.write_bytes(b"fixture")
        self.assertEqual(self.gate(2)["missing_required_recordings"], ["QA-001"])
        self.entry_json("qa-record", *finish, "--outcome", "PASS")
        self.assertEqual(self.gate(0)["missing_required_recordings"], [])
        path.write_bytes(b"replacement")
        self.assertEqual(self.gate(2)["missing_required_recordings"], ["QA-001"])
        self.plan["results"][0]["recording"] = str(path)
        self.assertEqual(self.gate(2)["missing_required_recordings"], ["QA-001"])

    def test_required_clip_must_match_case_round_attempt_and_outcome(self):
        self.recorded_plan(round_number=2)
        failed = self.record_clip(round_number=2, outcome="FAIL")
        other_case = self.record_clip(case="QA-002", round_number=2)
        earlier_round = self.record_clip()
        result = self.plan["results"][0]
        for wrong_clip in (failed, other_case, earlier_round):
            result["recording"] = wrong_clip
            self.assertEqual(self.gate(2)["missing_required_recordings"], ["QA-001"])
        result.update(recording=failed, attempt=2)
        self.assertEqual(self.gate(2)["missing_required_recordings"], ["QA-001"])
        result["recording"] = self.record_clip(round_number=2, attempt=2)
        self.assertEqual(self.gate(0)["missing_required_recordings"], [])

    def test_required_clip_can_be_carried_with_its_original_round_and_reason(self):
        self.recorded_plan(round_number=2)
        self.plan["results"][0].update(recording=self.record_clip(), recorded_round=1,
                                       evidence="evidence/round-1/QA-001-steps.md")
        self.assertEqual(self.gate(2)["missing_required_recordings"], ["QA-001"])
        self.plan["results"][0]["carry_over_reason"] = "The tested flow and its runtime are unchanged."
        self.assertEqual(self.gate(0)["missing_required_recordings"], [])

    def test_missing_recording_preserves_an_observed_failure(self):
        self.plan["scenarios"][0].update(kind="mobile", recording_required=True)
        self.plan["results"][0]["status"] = "FAIL"
        result = self.gate(1)
        self.assertEqual(result["failed_required"], ["QA-001"])
        self.assertEqual(result["missing_required_recordings"], ["QA-001"])

    def test_missing_optional_video_does_not_change_a_pass(self):
        self.plan["scenarios"][0].update(kind="browser", recording_required=False)
        self.plan["results"][0]["evidence"] = "evidence/round-1/QA-001-steps.md"
        self.evidence("evidence/round-1/QA-001-steps.md")
        self.assertEqual(self.gate(0)["missing_required_recordings"], [])

    def test_existing_gates_outside_git_skip_the_approval_check(self):
        self.assertEqual(self.gate(0)["approval_check"], "SKIPPED")

    def test_pass_with_missing_evidence_is_incomplete_but_fail_stays_fail(self):
        self.plan["results"][0]["evidence"] = "evidence/absent.json"
        result = self.gate(2)
        self.assertEqual(result["missing_evidence"], ["QA-001"])
        self.assertEqual(result["scenarios"][0]["status"], "INCOMPLETE")
        self.assertEqual(result["pending_required"], ["QA-001"])

        self.plan["results"][0]["status"] = "FAIL"
        result = self.gate(1)
        self.assertEqual(result["missing_evidence"], ["QA-001"])
        self.assertEqual(result["failed_required"], ["QA-001"])

    def test_evidence_must_stay_inside_the_folder_and_not_be_empty(self):
        (self.root / "outside.txt").write_text("outside", encoding="utf-8")
        self.gate_dir = self.root / "folder"
        self.gate_dir.mkdir()
        self.evidence("evidence/QA-002-cli.txt", "evidence/QA-003-ci.json")
        self.plan["results"][0]["evidence"] = "../outside.txt"
        self.assertEqual(self.gate(2)["missing_evidence"], ["QA-001"])

        self.plan["results"][0]["evidence"] = "evidence/empty.txt"
        (self.gate_dir / "evidence/empty.txt").write_text("", encoding="utf-8")
        self.assertEqual(self.gate(2)["missing_evidence"], ["QA-001"])

    def approved_plan(self, round_number=1):
        report = self.entry_json("reports", "--project", str(self.repo), "--task", "Approval gate")
        self.gate_dir = Path(report["directory"])
        self.evidence("evidence/QA-001-api.json", "evidence/QA-002-cli.txt", "evidence/QA-003-ci.json")
        self.evidence("qa-plan-round-1-rev-1.md")
        self.plan["round"] = round_number
        self.plan["approval"] = {"plan": "qa-plan-round-1-rev-1.md", "answer": "Approve"}
        self.base = datetime.now().replace(microsecond=0) - timedelta(hours=1)
        self.stamp("qa-plan-round-1-rev-1.md", self.base)

        for name in ("QA-001-api.json", "QA-002-cli.txt", "QA-003-ci.json"):
            self.stamp(f"evidence/{name}", self.base + timedelta(minutes=30))

    def answer(self, text, minutes):
        tasks.record(self.repo, "claude", "s", text, now=self.base + timedelta(minutes=minutes))

    def test_approval_is_skipped_without_task_records(self):
        self.approved_plan()
        result = self.gate(0)
        self.assertEqual(result["approval_check"], "SKIPPED")
        self.assertIn("approval_reason", result)

    def test_approval_is_skipped_when_task_capture_is_off(self):
        self.entry_json("config", "set", "captureTasks", "false", "--project", str(self.repo))
        self.approved_plan()
        self.answer("Something else", 5)
        self.assertEqual(self.gate(0)["approval_check"], "SKIPPED")

    def test_records_without_a_matching_answer_are_unverified(self):
        self.approved_plan()
        self.answer("Looks fine", 5)
        result = self.gate(2)
        self.assertEqual(result["approval_check"], "UNVERIFIED")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse(result["can_proceed"])

    def test_answer_recorded_before_the_plan_is_unverified(self):
        self.approved_plan()
        self.answer("Approve", -5)
        self.assertEqual(self.gate(2)["approval_check"], "UNVERIFIED")

    def test_missing_approval_object_with_records_is_unverified(self):
        self.approved_plan()
        self.answer("Approve", 5)
        self.plan.pop("approval")
        self.assertEqual(self.gate(2)["approval_check"], "UNVERIFIED")

    def test_chat_answer_after_the_plan_verifies_the_approval(self):
        self.approved_plan()
        self.answer("Approve", 5)
        result = self.gate(0)
        self.assertEqual(result["approval_check"], "VERIFIED")
        self.assertNotIn("approval_reason", result)
        self.assertEqual(result["evidence_before_approval"], [])

    def test_question_tool_answer_verifies_the_approval(self):
        self.approved_plan()
        self.answer("Q: Approve the QA plan for round 1, revision 1?\nA: Approve", 5)
        self.assertEqual(self.gate(0)["approval_check"], "VERIFIED")

    def test_evidence_older_than_the_approval_is_incomplete(self):
        self.approved_plan()
        self.answer("Approve", 40)
        result = self.gate(2)
        self.assertEqual(result["evidence_before_approval"], ["QA-001", "QA-002", "QA-003"])
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_carried_over_evidence_may_predate_the_approval(self):
        self.approved_plan(round_number=2)
        self.answer("Approve", 40)
        self.plan["results"][0]["recorded_round"] = 1
        result = self.gate(2)
        self.assertEqual(result["evidence_before_approval"], ["QA-002", "QA-003"])

        self.plan["results"][1:] = []
        self.plan["scenarios"][1:] = []
        self.plan["requirements"] = ["RC-001"]
        result = self.gate(0)
        self.assertEqual(result["evidence_before_approval"], [])
        self.assertEqual(result["approval_check"], "VERIFIED")

    def test_approval_belongs_to_the_newest_revision_of_its_round(self):
        self.approved_plan()
        self.answer("Approve", 5)
        self.evidence("qa-plan-round-2-rev-1.md")
        self.assertEqual(self.gate(0)["approval_check"], "VERIFIED")

        self.evidence("qa-plan-round-1-rev-2.md")
        result = self.gate(2)
        self.assertEqual(result["approval_check"], "UNVERIFIED")
        self.assertIn("qa-plan-round-1-rev-2.md", result["approval_reason"])

    def test_approved_plan_needs_the_revision_file_name(self):
        self.approved_plan()
        self.answer("Approve", 5)
        self.evidence("plan.md")
        self.stamp("plan.md", self.base)
        self.plan["approval"]["plan"] = "plan.md"
        self.assertEqual(self.gate(2)["approval_check"], "UNVERIFIED")

    def raw_answer(self, text, moment):
        folder = tasks.directory(self.repo, "main")
        folder.mkdir(parents=True, exist_ok=True)
        line = dict(ts=moment.isoformat(timespec="seconds"), client="claude", session="s", prompt=text)

        with open(folder / f"{datetime.now():%Y-%m-%d}.jsonl", "a", encoding="utf-8") as stream:
            stream.write(json.dumps(line) + "\n")

    def test_record_times_compare_as_absolute_instants(self):
        self.approved_plan()
        before = (self.base - timedelta(minutes=5)).astimezone(timezone(timedelta(hours=14)))
        self.raw_answer("Approve", before)
        self.assertEqual(self.gate(2)["approval_check"], "UNVERIFIED")

        self.raw_answer("Approve", (self.base + timedelta(minutes=5)).astimezone(timezone.utc))
        self.assertEqual(self.gate(0)["approval_check"], "VERIFIED")

    def test_legacy_records_without_offset_are_local_time(self):
        self.approved_plan()
        self.raw_answer("Approve", self.base + timedelta(minutes=5))
        self.assertEqual(self.gate(0)["approval_check"], "VERIFIED")
