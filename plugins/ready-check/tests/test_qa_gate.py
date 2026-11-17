import json

from helpers import RepoTest


class QAGateTest(RepoTest):
    def setUp(self):
        super().setUp()
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

    def gate(self, code):
        path = self.root / "qa-gate-input.json"
        path.write_text(json.dumps(self.plan), encoding="utf-8")
        return self.entry_json("qa-gate", "--input", str(path), code=code)

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
        self.assertEqual(self.gate(0)["scenarios"][-1]["kind"], "browser")
