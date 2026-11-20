import os
import unittest
from pathlib import Path

from helpers import RepoTest


class QaRecordTest(RepoTest):
    def prepare(self):
        result = self.entry_json("reports", "--project", str(self.repo), "--task", "Manual evidence")
        report = Path(result["report"])
        report.write_text("# QA report\n", encoding="utf-8")
        return result["task_id"], report.parent

    def step(self, task, round_number="1", case="QA-001", actor="agent", code=0, extra=()):
        return self.entry_json("qa-record", "--project", str(self.repo), "--task", task,
                               "--round", round_number, "--case", case, "--actor", actor,
                               "--action", "Submit [draft]", "--observed", "Appears <in list>\nRow count is 1",
                               *extra, code=code)

    def replay(self, task, video="QA-001.webm", code=0, extra=()):
        return self.entry_json("qa-replay", "--project", str(self.repo), "--task", task,
                               "--round", "1", "--case", "QA-001", "--video", video, *extra, code=code)

    def recording(self, task, name="QA-001.webm", code=0):
        return self.entry_json("qa-record", "--project", str(self.repo), "--task", task,
                               "--round", "1", "--case", "QA-001", "--prepare-video", name, code=code)

    def test_appends_executed_steps_and_keeps_rounds_separate(self):
        task, report = self.prepare()
        one = self.step(task)
        self.step(task, actor="user")
        two = self.step(task, round_number="2", actor="runner")
        self.assertEqual(one["evidence"], "evidence/round-1/QA-001-steps.md")
        self.assertEqual(Path(one["path"]), report / one["evidence"])
        original = Path(one["path"]).read_text(encoding="utf-8")
        self.assertRegex(original, r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ · agent")
        self.assertIn("· user ·", original)
        self.assertIn("  ~~~\n  Submit [draft]\n  ~~~", original)
        self.assertIn("  ~~~\n  Appears <in list>\n  Row count is 1\n  ~~~", original)
        self.assertEqual(original.count("**Observed**"), 2)
        self.assertIn("· runner ·", Path(two["path"]).read_text(encoding="utf-8"))
        self.assertEqual(self.git("status", "--short"), "")

    def test_requires_an_existing_report_and_safe_scenario_identity(self):
        missing = self.step("missing report", code=2)
        self.assertIn("Prepare the task report", missing["reason"])
        self.assertFalse((self.repo / ".ai").exists())
        task, report = self.prepare()
        for round_number, case in (("0", "QA-001"), ("1", "../QA-001")):
            result = self.step(task, round_number=round_number, case=case, code=2)
            self.assertIn("scenario ID", result["reason"])
        self.assertFalse((report / "evidence").exists())

    def test_replay_links_timed_steps_and_keeps_other_observations(self):
        task, _ = self.prepare()
        one = self.step(task, extra=("--expected", "Title <script>alert(1)</script>"))
        self.step(task, actor="user")
        journal = Path(one["path"])
        (journal.parent / "QA-001.webm").write_bytes(b"video fixture")
        result = self.replay(task, extra=("--at", f"{one['step_id']}=7.25"))
        self.assertEqual(result["evidence"], "evidence/round-1/QA-001.webm-replay.html")
        page = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn('src="QA-001.webm"', page)
        self.assertIn('href="QA-001-steps.md"', page)
        self.assertEqual(page.count('data-at="7.250"'), 1)
        self.assertIn(">00:07</button>", page)
        self.assertIn("Title &lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("Title <script>", page)
        self.assertEqual(page.count("<h2>Submit [draft]</h2>"), 2)
        self.assertIn('data-at="7.250"', Path(self.replay(task)["path"]).read_text(encoding="utf-8"))

    def test_offsets_are_bound_to_the_finished_clip(self):
        task, _ = self.prepare()
        first = self.step(task)
        second = self.step(task, extra=("--attempt", "2", "--observed", "Retry succeeded"))
        clip_a = Path(self.recording(task, "QA-001-attempt-1.webm")["path"])
        clip_b = Path(self.recording(task, "QA-001-attempt-2.webm")["path"])
        clip_a.write_bytes(b"first recording")
        clip_b.write_bytes(b"second recording")
        first_replay = self.replay(task, clip_a.name, extra=("--at", f"{first['step_id']}=3"))
        first_page = Path(first_replay["path"]).read_text(encoding="utf-8")
        self.assertIn("Attempt 1", first_page)
        self.assertNotIn("Retry succeeded", first_page)
        second_replay = self.replay(task, clip_b.name, extra=("--at", f"{second['step_id']}=6"))
        page = Path(second_replay["path"]).read_text(encoding="utf-8")
        self.assertNotIn('data-at="3.000"', page)
        self.assertIn('data-at="6.000"', page)
        self.assertIn("Attempt 2", page)
        self.assertIn("Retry succeeded", page)
        self.assertNotIn("Row count is 1", page)
        self.assertIn("unique step_id", self.replay(task, clip_a.name, code=2,
                                                   extra=("--at", f"{second['step_id']}=4"))["reason"])
        self.assertIn("new video filename", self.recording(task, clip_a.name, code=2)["reason"])
        clip_a.write_bytes(b"externally replaced clip")
        page = Path(self.replay(task, clip_a.name)["path"]).read_text(encoding="utf-8")
        self.assertNotIn("data-at=", page)

    def test_retry_keeps_the_same_attempt_number_in_its_recording_and_journal(self):
        task, _ = self.prepare()
        args = ("--project", str(self.repo), "--task", task, "--round", "1", "--case", "QA-001")
        rejected = self.entry_json("qa-record", *args, "--attempt", "2", "--prepare-video",
                                   "QA-001-attempt-1.webm", code=2)
        self.assertIn("selected attempt", rejected["reason"])
        prepared = self.recording(task, "QA-001-attempt-2.webm")
        Path(prepared["path"]).write_bytes(b"capture")
        self.step(task)
        finish = (*args, "--finish-video", prepared["video"])
        result = self.entry_json("qa-record", *finish, "--outcome", "PASS", code=2)
        self.assertIn("no recorded steps for attempt 2", result["reason"])
        retry = self.step(task, extra=("--attempt", "2"))
        self.assertEqual(self.entry_json("qa-record", *finish, "--outcome", "PASS")["attempt"], 2)
        self.entry_json("qa-record", *finish, "--outcome", "PASS")
        result = self.entry_json("qa-record", *finish, "--outcome", "FAIL", code=2)
        self.assertIn("different outcome", result["reason"])
        self.assertEqual(Path(retry["path"]).read_text(encoding="utf-8").count("<!-- qa-recording:"), 1)

    def test_recording_directory_keeps_extra_tab_clips_private(self):
        task, _ = self.prepare()
        step = self.step(task)
        prepared = self.recording(task, "QA-001-attempt-1.webm")
        self.assertIn("new video filename", self.recording(task, "QA-001-attempt-1.webm", code=2)["reason"])
        directory = Path(prepared["directory"])
        self.assertEqual(list(directory.iterdir()), [])
        primary = Path(prepared["path"])
        secondary = directory / "QA-001-attempt-1-1.webm"
        (self.repo / ".gitignore").write_text(f"!/{secondary.relative_to(self.repo).as_posix()}\n", encoding="utf-8")
        primary.write_bytes(b"main tab")
        secondary.write_bytes(b"second tab")
        self.assertEqual(self.git("status", "--short", "--untracked-files=all"), "?? .gitignore\n")

        result = self.replay(task, f"{directory.name}/{secondary.name}", extra=("--at", f"{step['step_id']}=6"))
        page = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn(f'src="{secondary.name}"', page)
        self.assertIn('href="../QA-001-steps.md"', page)
        self.assertIn('data-at="6.000"', page)
        result = self.replay(task, prepared["video"])
        self.assertNotIn('data-at=', Path(result["path"]).read_text(encoding="utf-8"))

    def test_replays_keep_webm_and_mp4_with_the_same_stem_separate(self):
        task, _ = self.prepare()
        self.step(task)
        players = []
        for extension in ("webm", "mp4"):
            prepared = self.recording(task, f"QA-001-attempt-1.{extension}")
            Path(prepared["path"]).write_bytes(extension.encode())
            result = self.replay(task, prepared["video"])
            players.append(Path(result["path"]))
        self.assertNotEqual(*players)
        for player, extension in zip(players, ("webm", "mp4")):
            self.assertIn(f'src="QA-001-attempt-1.{extension}"', player.read_text(encoding="utf-8"))

    def test_preserves_significant_whitespace_for_cli_evidence(self):
        task, _ = self.prepare()
        action = "  python export.py --file 'My  Draft.csv'"
        observed = "Created  2 items\r\n\tOK  \r\n\r\n~~~\r\n<output>&copy;</output>"
        result = self.entry_json("qa-record", "--project", str(self.repo), "--task", task, "--round", "1",
                                 "--case", "QA-001", "--action", action, "--observed", observed)
        path = Path(result["path"])
        journal = path.read_text(encoding="utf-8")
        self.assertIn(f"  ~~~\n  {action}\n  ~~~", journal)
        self.assertIn("  ~~~~\n  Created  2 items\n  \tOK  \n  \n  ~~~\n  <output>&copy;</output>\n  ~~~~", journal)
        (path.parent / "QA-001.webm").write_bytes(b"fixture")
        page = Path(self.replay(task)["path"]).read_text(encoding="utf-8")
        self.assertIn("Created  2 items\n\tOK  \n\n~~~\n&lt;output&gt;&amp;copy;&lt;/output&gt;", page)

    def test_replay_reads_legacy_entries_appended_with_new_entries(self):
        task, _ = self.prepare()
        step = self.step(task)
        journal = Path(step["path"])
        legacy = ("- 2026-11-20T12:00:00Z · runner · **Legacy \\[draft\\]**\n"
                  "  Observed: first&#10;second  line\n")
        journal.write_text(legacy + journal.read_text(encoding="utf-8"), encoding="utf-8")
        (journal.parent / "QA-001.webm").write_bytes(b"fixture")
        page = Path(self.replay(task)["path"]).read_text(encoding="utf-8")
        self.assertIn("first\nsecond  line", page)
        self.assertLess(page.index("Legacy [draft]"), page.index("Submit [draft]"))

    def test_recovers_missing_git_exclusion_before_creating_evidence(self):
        task, _ = self.prepare()
        (self.repo / ".git/info/exclude").write_text("# restored fixture\n", encoding="utf-8")
        self.step(task)
        planned = self.recording(task, "QA-001-retry.webm")
        Path(planned["path"]).write_bytes(b"private fixture")
        self.assertEqual(self.git("status", "--short", "--untracked-files=all"), "")

    def test_refuses_a_recording_directory_exposed_by_gitignore(self):
        task, report = self.prepare()
        (self.repo / ".gitignore").write_text(
            "!/.ai/ready-check/\n!/.ai/ready-check/**/\n/.ai/ready-check/**/*.webm\n"
            "/.ai/ready-check/**/*-steps.md\n!/.ai/ready-check/**/QA-001-1.webm\n", encoding="utf-8")
        reason = self.recording(task, code=2)["reason"]
        self.assertIn("entire QA recording directory", reason)
        self.assertFalse((report / "evidence/round-1/QA-001.webm.capture").exists())

    def test_refuses_to_reserve_a_directory_with_an_already_tracked_clip(self):
        task, _ = self.prepare()
        prepared = self.recording(task)
        clip = Path(prepared["directory"]) / "QA-001-1.webm"
        clip.write_bytes(b"fixture")
        self.git("add", "-f", "--", clip.relative_to(self.repo).as_posix())
        clip.unlink()
        clip.parent.rmdir()
        self.assertIn("untracked and ignored", self.recording(task, code=2)["reason"])
        self.assertFalse(clip.parent.exists())

    def test_replay_requires_local_case_video_and_finite_offsets(self):
        task, report = self.prepare()
        self.assertFalse((report / "evidence").exists())
        self.assertIn("round folder", self.replay(task, video="../other.webm", code=2)["reason"])
        step = self.step(task)
        self.assertIn("Missing or empty", self.replay(task, code=2)["reason"])
        Path(self.recording(task)["path"]).write_bytes(b"fixture")
        for invalid in ("-1", "inf", "nan"):
            result = self.replay(task, code=2, extra=("--at", f"{step['step_id']}={invalid}"))
            self.assertIn("nonnegative", result["reason"])
        self.assertFalse(list(report.rglob("*-replay.html")))

    @unittest.skipIf(os.name == "nt", "Creating symlinks may require Windows Developer Mode")
    def test_refuses_symlinked_evidence_destination(self):
        task, report = self.prepare()
        outside = self.root / "outside"
        outside.mkdir()
        (report / "evidence").symlink_to(outside, target_is_directory=True)
        self.assertIn("real directory", self.step(task, code=2)["reason"])
        self.assertIn("real directory", self.replay(task, code=2)["reason"])
        self.assertEqual(list(outside.iterdir()), [])
