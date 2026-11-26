import json
import re
import stat
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from helpers import PLUGIN, TempHome
from test_cli import run
from test_loading import install_fixtures
from test_profile import AXES
import digest
import profiles
import report

TODAY = date(2026, 11, 16)


def portrait(data, **changes):
    ids = [item["id"] for item in data["evidence"]]
    result = {
        "schema_version": 1, "language": "en", "summary": "You plan first and verify often.",
        "axes": [{"id": axis["id"], "score": 6.5, "reason": "Steady", "evidence": ids[:2]} for axis in AXES],
        "strengths": [{"title": "Clear starts", "detail": "Goals stated up front", "tip": "Keep it", "evidence": ids[:2]}],
        "growth": [{"title": "Fewer restarts", "detail": "Corrections follow vague asks", "tip": "Name the file",
                    "evidence": ids[:1], "cause": "Two corrections after unnamed files"}],
        "observations": [{"title": "Late sessions", "detail": "Most work after 18:00"}],
        "themes": [{"project": "shop", "topics": ["checkout coupons"]}],
        "archetype": None,
        "coverage": {"uncovered_share": 0.2, "note": "Most work fits the axes"},
    }
    result.update(changes)
    return result


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)
        install_fixtures(self.home)
        profiles.set_axes(AXES, "web shops", "developer")
        self.profile = profiles.read()
        self.digest = digest.build("month", TODAY)

    def test_accepts_valid_portrait(self):
        self.assertEqual(report.validate(portrait(self.digest), self.digest, self.profile), [])

    def test_only_growth_findings_require_and_display_a_next_step(self):
        data = portrait(self.digest)
        strength, growth = data["strengths"][0], data["growth"][0]
        strength["tip"] = "Legacy strength advice from fixture"
        self.assertFalse(strength["tip"] in self.html(data))
        strength.pop("tip")
        self.assertEqual(report.validate(data, self.digest, self.profile), [])
        page = self.html(data)
        self.assertEqual(page.count('<div class="finding-action">'), 1)
        self.assertIn("<strong>Next step</strong>", page)
        self.assertIn("Name the file", page)
        growth.pop("tip")
        self.assertIn("growth 1: needs tip", report.validate(data, self.digest, self.profile))

    def test_rejects_unknown_evidence(self):
        data = portrait(self.digest)
        data["strengths"][0]["evidence"] = ["cc-deadbeef", self.digest["evidence"][0]["id"]]
        problems = report.validate(data, self.digest, self.profile)
        self.assertTrue(any("cc-deadbeef" in problem for problem in problems), problems)

    def test_rejects_single_evidence_without_cause(self):
        data = portrait(self.digest)
        data["growth"][0].pop("cause")
        self.assertTrue(report.validate(data, self.digest, self.profile))

    def test_rejects_too_many_findings(self):
        data = portrait(self.digest)
        data["strengths"] = data["strengths"] * 6
        self.assertTrue(report.validate(data, self.digest, self.profile))

    def test_rejects_unknown_axis(self):
        data = portrait(self.digest)
        data["axes"][0]["id"] = "dancing"
        problems = report.validate(data, self.digest, self.profile)
        self.assertTrue(any("dancing" in problem for problem in problems), problems)

    def test_rejects_score_out_of_range(self):
        data = portrait(self.digest)
        data["axes"][0]["score"] = 11
        self.assertTrue(report.validate(data, self.digest, self.profile))

    def test_rejects_invalid_ui_labels_and_placeholders(self):
        data = portrait(self.digest, language="de", ui={"evidence": "{count.__class__}", "unknown": "Text",
                                                        "try": False, "previous_score": "Früher"})
        problems = report.validate(data, self.digest, self.profile)
        for key in ("evidence", "unknown", "try", "previous_score"):
            self.assertTrue(any(key in problem for problem in problems), problems)

    def test_metrics_only_rejects_axes(self):
        data = digest.build("month", TODAY, metrics_only=True)
        self.assertTrue(report.validate(portrait(self.digest), data, self.profile))
        quiet = portrait(data, axes=[], strengths=[{"title": "Finishes", "detail": "8 of 10", "tip": "Keep", "evidence": [],
                                                    "cause": "completion 8.0"}], growth=[])
        self.assertEqual(report.validate(quiet, data, self.profile), [])

    def test_archetype_needs_scores(self):
        data = portrait(self.digest, archetype={"lead": "architect", "second": None, "text": "Plans"})
        self.assertTrue(report.validate(data, self.digest, self.profile))
        styled = digest.build("month", TODAY, archetypes_on=True)
        self.assertEqual(report.validate(portrait(styled, archetype={"lead": "architect", "second": "sprinter",
                                                                     "text": "Plans"}), styled, self.profile), [])

    def html(self, data=None, **changes):
        return report.render_html(self.digest, data or portrait(self.digest, **changes), self.profile, None)

    def test_html_is_offline(self):
        page = self.html()
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("default-src 'none'", page)
        library = (PLUGIN / "report/vendor/chart.umd.min.js").read_text(encoding="utf-8")
        self.assertIn(library, page)
        rest = page.replace(library, "")
        self.assertNotRegex(rest, r"https?://")
        self.assertNotIn("<link", rest)
        self.assertNotRegex(rest, r"\ssrc=")
        self.assertIn("Chart.defaults.animation = false", rest)

    def test_html_escapes_text(self):
        data = portrait(self.digest)
        data["strengths"][0]["title"] = "<script>alert(1)</script>"
        page = self.html(data)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)", page)

    def test_html_blocks(self):
        page = self.html()

        for marker in ('id="profile-radar"', 'id="axis-p-framing"', 'id="axis-u-clarity"', 'id="finding-1"',
                       "Clear starts", "Fewer restarts", "Cursor not counted", "Local, confidential report",
                       "<details", "Add pagination to the users endpoint"):
            self.assertIn(marker, page)

        self.assertNotIn('id="style-radar"', page)

    def test_html_shows_edit_check_counts_and_missing_rate(self):
        self.digest["current"]["summary"].update(edit_sessions=8, checks_after_edit_sessions=3)
        page = self.html()
        self.assertIn("Checks after edits", page)
        self.assertIn('<tr><td>This period</td><td class="num">8</td><td class="num">3</td>', page)
        self.assertIn('<td class="num">37.5%</td>', page)
        self.assertIn('<tr><td>Previous period</td><td class="num">0</td><td class="num">0</td>'
                      '<td class="num">—</td>', page)

    def test_localized_report_labels_and_ranked_archetypes(self):
        styled = digest.build("month", TODAY, archetypes_on=True)
        styled["current"]["archetypes"].update(architect=2.0, delegator=9.0)
        data = portrait(styled, language="de-DE", ui={
            "title": "Gnothi-Bericht", "try": "Versuch", "evidence": "Belege ({count})",
            "current_period": "Aktueller Zeitraum", "previous_period": "Vorheriger Zeitraum",
            "architect": "Architekt", "delegator": "Delegierer", "work_style": "Arbeitsstil",
        })
        data["axes"][0].update(name="Aufgabenstellung", measures="Ziele und Vorgaben")
        self.assertEqual(report.validate(data, styled, self.profile), [])
        page = report.render_html(styled, data, self.profile, None)
        self.assertIn('<html lang="de-DE">', page)
        self.assertIn('<title>Gnothi-Bericht</title>', page)
        self.assertIn('<h4>Aufgabenstellung</h4><p class="axis-meaning">Ziele und Vorgaben</p>', page)
        self.assertIn("<strong>Versuch</strong>", page)
        self.assertIn("<summary>Belege (2)</summary>", page)
        self.assertIn("Aktueller Zeitraum (2026-10-18 – 2026-11-16)", page)
        self.assertIn("Vorheriger Zeitraum (2026-09-18 – 2026-10-17)", page)
        self.assertIn('<ol class="style-scores" role="list"><li><span>Delegierer</span><strong>9.0 / 10</strong>', page)
        self.assertNotIn("For fun:", page)
        chart = json.loads(re.search(r"const DATA = (.*);", page).group(1))
        self.assertEqual(chart["style"]["labels"][0], "Delegierer")
        self.assertEqual(chart["style"]["title"], "Arbeitsstil")
        self.assertEqual(chart["radar"]["labels"][0], "Aufgabenstellung")

    def test_earlier_personal_scores_keep_their_own_dates(self):
        self.digest["previous"]["axes"] = dict(clarity=7.0, focus=8.0, completion=9.0, tool_range=1.0)
        data = portrait(self.digest)
        previous = {"start": "2026-09-19", "end": "2026-10-18", "axes": {data["axes"][0]["id"]: 4.0}}
        page = report.render_html(self.digest, data, self.profile, previous)
        radar = json.loads(re.search(r"const DATA = (.*);", page).group(1))["radar"]
        self.assertEqual(radar["previous_label"], "Previous period (2026-09-18 – 2026-10-17)")
        self.assertIsNone(radar["previous"][0])
        self.assertEqual(radar["earlier"][0], 4.0)
        self.assertEqual(radar["earlier_label"], "Earlier portrait (2026-09-19 – 2026-10-18)")
        self.assertIn('<strong class="score">6.5</strong><span class="prior-score">Previous: 4.0 · 2026-09-19', page)
        self.assertIn('<details class="axis-reason"><summary>Why 6.5</summary><p>Steady</p>', page)

    def test_section_links_and_highlights_follow_available_content(self):
        page = self.html()
        navigation = re.search(r'<nav class="section-nav"[^>]*>(.*?)</nav>', page).group(1)
        self.assertEqual(re.findall(r'href="#([^"]+)"', navigation), ["summary", "profile", "findings", "stats"])
        highlights = re.search(r'<section class="report-section" id="summary">(.*?)</section>', page).group(1)
        self.assertEqual(re.findall(r'href="#([^"]+)"', highlights), ["finding-1", "finding-2"])
        empty = self.html(strengths=[], growth=[])
        self.assertNotIn('href="#summary"', empty)
        self.assertNotIn('id="summary"', empty)

    def test_score_bars_keep_zero_and_only_mark_aligned_comparisons(self):
        rows = [
            ("axis-p-zero", "Zero", "Measure", 0, 1, None, None, None),
            ("axis-p-missing", "Missing", "Measure", None, 3, "2026-09-01", None, None),
        ]
        page = report.render_axes(rows, {}, report.strings_for({}))
        self.assertIn('width:0%', page)
        self.assertIn('inset-inline-start:10%', page)
        self.assertIn('aria-label="Declined -1.0"', page)
        self.assertNotIn('inset-inline-start:30%', page)
        self.assertIn('<strong class="score">—</strong>', page)

    def test_trend_needs_two_months(self):
        data = digest.build("all", TODAY)
        self.assertNotIn('id="trend"', report.render_html(data, portrait(data), self.profile, None))
        data["trend"].append({"month": "2026-12", "axes": data["trend"][0]["axes"]})
        self.assertIn('id="trend"', report.render_html(data, portrait(data), self.profile, None))

    def test_coverage_banner(self):
        self.assertIn("update your profile", self.html(coverage={"uncovered_share": 0.7, "note": "Mostly writing"}))
        self.assertNotIn("update your profile", self.html())

    def test_previous_from_history(self):
        epoch = profiles.current_epoch(self.profile)["id"]
        lines = [
            {"date": "2026-10-16", "period": "month", "epoch": epoch, "start": "2026-09-17", "end": "2026-10-16",
             "axes": {"framing": 4.0}, "universal": {}},
            {"date": "2026-11-10", "period": "month", "epoch": epoch, "start": "2026-10-12", "end": "2026-11-10",
             "axes": {"framing": 9.0}, "universal": {}},
            {"date": "2026-10-17", "period": "year", "epoch": epoch, "start": "2025-10-18", "end": "2026-10-17",
             "axes": {"framing": 1.0}, "universal": {}},
        ]
        path = self.home.root / "data/history.jsonl"
        path.write_text("".join(json.dumps(line) + "\n" for line in lines))
        self.assertEqual(report.previous_entry(self.digest, epoch)["axes"], {"framing": 4.0})
        self.assertIsNone(report.previous_entry(self.digest, epoch + 1))


class RenderCliTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)
        install_fixtures(self.home)
        profiles.set_axes(AXES, "web shops", "developer")

        with mock.patch("digest.date") as clock:
            clock.today.return_value = TODAY
            self.digest = run("collect", "--period", "month")[1]

    def write(self, data):
        path = self.home.root / "data/tmp/portrait.json"
        path.write_text(json.dumps(data))
        return path

    def test_render_writes_history_and_report(self):
        self.write(portrait(self.digest))
        code, result = run("render")
        self.assertEqual((code, result["status"]), (0, "PASS"), result)
        path = self.home.root / "data/reports" / f"portrait-month-{date.today().isoformat()}.html"
        self.assertEqual(result["html"], str(path))
        self.assertNotIn("widget_id", result)
        self.assertTrue(path.is_file())
        history = (self.home.root / "data/history.jsonl").read_text().splitlines()
        self.assertEqual(len(history), 1)
        self.assertEqual(json.loads(history[0])["axes"]["framing"], 6.5)

        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_render_with_metrics_opt_in_prepares_both_html_reports(self):
        self.write(portrait(self.digest))
        code, result = run("render", "--widget-metrics", self.digest["digest_id"])
        self.assertEqual((code, result["status"]), (0, "PASS"), result)
        self.assertTrue(Path(result["html"]).is_file())
        widget = Path(result["widget_html"])
        self.assertIn(result["widget_id"], widget.name)
        self.assertIn("Aggregate metrics from the selected period", widget.read_text(encoding="utf-8"))
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(widget.stat().st_mode), 0o600)

    def test_non_english_reports_require_labels_and_use_them_in_both_views(self):
        data = portrait(self.digest, language="fr")
        data["ui"] = {"title": "Portrait de travail"}
        self.write(data)
        code, result = run("render")
        self.assertEqual((code, result["status"]), (2, "FAIL"))
        self.assertIn("translate all report labels", result["reason"])
        self.assertFalse((self.home.root / "data/history.jsonl").exists())

        from report_strings import REPORT_LABELS, placeholders
        data["ui"] = {key: "Libellé " + " ".join("{" + name + "}" for name in sorted(placeholders(value)))
                      for key, value in REPORT_LABELS.items()}
        data["ui"]["title"] = "Portrait de travail"
        data["ui"]["metrics_title"] = "Portrait en chiffres"
        self.write(data)
        code, result = run("render", "--widget-metrics", self.digest["digest_id"])
        self.assertEqual((code, result["status"]), (0, "PASS"), result)
        full = Path(result["html"]).read_text(encoding="utf-8")
        metrics = Path(result["widget_html"]).read_text(encoding="utf-8")
        self.assertIn('lang="fr"', full)
        self.assertIn("<title>Portrait de travail</title>", full)
        self.assertIn("Portrait en chiffres", metrics)
        self.assertNotIn("Aggregate metrics from the selected period.", metrics)

    def test_metrics_opt_in_rejects_a_digest_replaced_after_collection(self):
        self.write(portrait(self.digest))
        code, newer = run("collect", "--period", "all")
        self.assertEqual(code, 0, newer)
        self.assertNotEqual(newer["digest_id"], self.digest["digest_id"])
        code, result = run("render", "--widget-metrics", self.digest["digest_id"])
        self.assertEqual((code, result["status"]), (2, "FAIL"))
        self.assertIn("approved Gnothi digest changed", result["reason"])
        self.assertNotIn("widget_id", result)
        self.assertFalse((self.home.root / "data/history.jsonl").exists())

    def test_render_fails_on_invalid(self):
        data = portrait(self.digest)
        data["axes"][0]["evidence"] = ["cu-00000000"]
        code, result = run("render", "--portrait", str(self.write(data)))
        self.assertEqual((code, result["status"]), (2, "FAIL"))
        self.assertIn("cu-00000000", result["reason"])
        self.assertFalse((self.home.root / "data/history.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
