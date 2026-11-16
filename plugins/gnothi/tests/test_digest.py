import json
import unittest
from datetime import date

from helpers import TempHome
from test_loading import install_fixtures
import digest

TODAY = date(2026, 11, 16)
KEYS = {"schema_version", "period", "sources", "metrics_only", "current", "previous", "trend", "activity", "tools",
        "friction", "tokens", "projects", "evidence"}


class DigestTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)
        install_fixtures(self.home)

    def test_shape_for_month(self):
        data = digest.build("month", TODAY)
        self.assertEqual(set(data), KEYS)
        self.assertEqual(data["period"], {"name": "month", "start": "2026-10-18", "end": "2026-11-16",
                                          "previous": {"start": "2026-09-18", "end": "2026-10-17"}})
        self.assertEqual(data["current"]["summary"]["sessions"], 3)
        self.assertEqual(data["current"]["summary"]["edit_sessions"], 1)
        self.assertEqual(data["current"]["summary"]["checks_after_edit_sessions"], 0)
        self.assertEqual(set(data["current"]["axes"]), {"clarity", "focus", "completion", "tool_range"})
        self.assertIsNone(data["current"]["archetypes"])
        self.assertEqual(data["previous"]["summary"]["sessions"], 0)
        self.assertEqual(data["trend"], [])
        self.assertEqual(data["tokens"], {"claude": 140, "codex": 1000, "cursor": None, "note": "Cursor not counted"})
        self.assertEqual(sorted(item["name"] for item in data["projects"]), ["api", "blog", "shop"])
        self.assertEqual(len(data["evidence"]), 3)
        self.assertEqual(len({item["id"] for item in data["evidence"]}), 3)
        self.assertEqual(data["friction"]["corrections"], 3)
        json.dumps(data)

    def test_source_counts_cover_current_period_only(self):
        data = digest.build("month", date(2026, 12, 20))
        self.assertEqual(data["previous"]["summary"]["sessions"], 3)
        self.assertEqual([item["sessions"] for item in data["sources"]], [0, 0, 0])

    def test_all_has_trend_and_no_previous(self):
        data = digest.build("all", TODAY, archetypes_on=True)
        self.assertIsNone(data["previous"])
        self.assertEqual([item["month"] for item in data["trend"]], ["2026-11"])
        self.assertEqual(len(data["current"]["archetypes"]), 6)

    def test_evidence_excerpts(self):
        item = next(entry for entry in digest.build("month", TODAY)["evidence"] if entry["client"] == "claude")
        self.assertEqual(item["excerpts"][0], "Add a coupon field to the checkout form")
        self.assertIn("no, I meant the other file", item["excerpts"])
        self.assertLessEqual(len(item["excerpts"]), 3)
        self.assertIn("correction", item["flags"])
        self.assertEqual((item["project"], item["date"], item["turns"]), ("shop", "2026-11-10", 3))

    def test_budget_is_respected(self):
        self.assertEqual(digest.build("month", TODAY, budget=0)["evidence"], [])
        full = digest.build("month", TODAY)
        size = len(json.dumps(dict(full, evidence=[]), ensure_ascii=False))
        budget = (size + len(json.dumps(full["evidence"][0], ensure_ascii=False)) + 8) // 4 + 1
        data = digest.build("month", TODAY, budget=budget)
        self.assertEqual(len(data["evidence"]), 1)
        self.assertLessEqual(len(json.dumps(data, ensure_ascii=False)), budget * 4)

    def test_metrics_only_has_no_text(self):
        text = json.dumps(digest.build("month", TODAY, metrics_only=True), ensure_ascii=False)

        for word in ("coupon", "pagination", "caching", "shop", "blog", '"api"', "I meant"):
            self.assertNotIn(word, text)

        self.assertIn("project-1", text)


if __name__ == "__main__":
    unittest.main()
