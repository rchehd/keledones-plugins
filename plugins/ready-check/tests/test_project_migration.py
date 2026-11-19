import errno
import json
import os
import shutil
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event, local
from unittest.mock import patch

from helpers import RepoTest
import customize
import hook
import project
import reports
import rules
import tasks
from project import BASE, LEGACY_BASE
from reports import slug


class MigrationTest(RepoTest):
    def setUp(self):
        super().setUp()
        self.old = self.repo / LEGACY_BASE
        self.new = self.repo / BASE

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def start(self):
        return self.entry_json("hook", "session-start", "--client", "claude",
                               stdin=json.dumps({"cwd": str(self.repo), "session_id": "upgrade"}))

    def test_upgrade_preserves_reports_and_reads_previous_settings(self):
        task = "test-migration-2026-11-19"
        folder = Path("reports") / slug("main") / task
        self.write(self.old / "settings.json", json.dumps({"remind": False, "commitTemplate": "ai/ready-check/message.txt"}))
        self.write(self.old / "message.txt", "Previous template\n")
        evidence = self.write(self.old / folder / "evidence" / "checks (test).log", "Saved evidence\n")
        moved = self.new / evidence.relative_to(self.old)
        report = self.write(self.old / folder / "report.md", f"[Saved evidence](<{evidence.as_posix()}>)\n")
        self.write(self.old / folder / "doctor.json", json.dumps({"checks": [{"evidence": [str(evidence)]}]}))
        mtime = report.stat().st_mtime_ns
        self.write(self.old.parent / "unrelated.txt", "Keep\n")

        before = self.entry_json("config", "get", "remind", "--project", str(self.repo))
        self.assertFalse(before["settings"]["remind"])
        self.assertFalse(self.new.exists())
        result = self.entry_json("reports", "--project", str(self.repo), "--task", task)
        self.assertEqual(Path(result["report"]), self.new / folder / "report.md")
        self.assertEqual(Path(result["report"]).read_text(), f"[Saved evidence](<{moved.as_posix()}>)\n")
        self.assertEqual(Path(result["report"]).stat().st_mtime_ns, mtime)
        self.assertEqual(moved.read_text(), "Saved evidence\n")
        doctor = self.new / folder / "doctor.json"
        self.assertEqual(json.loads(doctor.read_text())["checks"][0]["evidence"], [str(moved)])
        self.assertFalse(self.old.exists())
        self.assertTrue((self.old.parent / "unrelated.txt").is_file())
        self.assertIn("/.ai/ready-check/", (self.repo / ".git/info/exclude").read_text())
        template = self.entry_json("template", "commit", "--project", str(self.repo))
        self.assertEqual(template["content"], "Previous template\n")
        self.start()
        self.assertFalse(self.old.exists())

    def test_session_upgrade_preserves_tracked_files_and_both_conflicting_copies(self):
        shared = self.write(self.old / "rules.md", "- Keep shared rules\n")
        self.git("add", "-f", str(shared))
        self.git("commit", "-m", "Add shared rules")
        self.write(self.old / "settings.json", '{"remind": false}\n')
        self.write(self.new / "settings.json", '{"remind": true}\n')
        self.write(self.old / "feedback.jsonl", '{"returned": true}\n')

        result = self.start()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Keep shared rules", result)
        self.assertEqual((self.old / "settings.json").read_text(), '{"remind": false}\n')
        self.assertEqual((self.new / "settings.json").read_text(), '{"remind": true}\n')
        self.assertTrue(shared.is_file())
        self.assertFalse((self.new / "rules.md").exists())
        self.assertTrue((self.new / "feedback.jsonl").is_file())
        self.assertEqual(self.git("status", "--short"), "")
        self.start()
        self.assertTrue(shared.is_file())

    def test_session_upgrade_keeps_a_tracked_profile_confirmed(self):
        settings = self.write(self.old / "settings.json", '{"profile":"generic","runner":"local","application":"."}\n')
        self.git("add", "-f", str(settings))
        self.git("commit", "-m", "Share Ready Check profile")

        with patch.object(hook, "browser_status", return_value="ready"):
            output = hook.session_start("claude", {"cwd": str(self.repo), "session_id": "upgrade"})

        self.assertNotIn("Ready Check detected:", output["hookSpecificOutput"]["additionalContext"])
        self.assertTrue(settings.is_file())
        self.assertFalse((self.new / "settings.json").exists())

    def test_project_writes_keep_shared_rules_and_checklists_current(self):
        shared = self.write(self.old / "rules.md", "- Prefer strict types\n")
        review = self.write(self.old / "extensions/generic/review.md", "## Team\n- [ ] Existing check\n")
        self.git("add", "-f", str(shared), str(review))
        self.git("commit", "-m", "Share Ready Check configuration")
        self.entry_json("rules", "add", "Local rule", "--project", str(self.repo))
        self.assertEqual((self.new / "rules.md").read_text(), "- Local rule\n")
        customize.add("review", "Local check", "project", self.repo, "generic")

        self.write(shared, "- MUST: Prefer strict types\n- MUST: Keep coverage\n")
        self.write(review, "## Team\n- [ ] Updated check\n")
        self.git("add", "-u")
        self.git("commit", "-m", "Refresh the shared checks")
        self.assertEqual({rule["text"]: rule["must"] for rule in rules.load(self.repo)},
                         {"Local rule": False, "Prefer strict types": True, "Keep coverage": True})
        self.assertEqual({item["text"] for item in customize.load(self.repo, "review", "generic")},
                         {"Local check", "Updated check"})

    def test_colliding_logs_are_read_from_both_locations_and_deduplicated(self):
        day = date.today().isoformat()
        journal = Path("tasks") / slug("main") / f"{day}.jsonl"

        for relative, field in ((journal, "prompt"), (Path("feedback.jsonl"), "reason")):
            common = dict(ts=f"{day}T10:00:00", session="fixture", **{field: "common"})
            for root, hour, value in ((self.old, 11, "legacy"), (self.new, 12, "current")):
                recent = dict(ts=f"{day}T{hour}:00:00", session="fixture", **{field: value})
                self.write(root / relative, "\n".join(json.dumps(record) for record in (common, recent)) + "\n")

        self.start()
        result = self.entry_json("tasks", "--project", str(self.repo), "--limit", "3")
        self.assertEqual(result["sessions"][0]["prompts"], ["common", "legacy", "current"])
        result = self.entry_json("feedback", "list", "--project", str(self.repo), "--limit", "3")
        self.assertEqual([record["reason"] for record in result["records"]], ["current", "legacy", "common"])
        self.assertTrue((self.old / journal).is_file())
        self.assertTrue((self.old / "feedback.jsonl").is_file())

    def test_upgrade_uses_a_staged_copy_across_filesystems(self):
        original = self.write(self.old / "settings.json", '{"remind": false}\n')
        rename = Path.rename

        def cross_device(source, target):
            if source == original:
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return rename(source, target)

        with patch.object(Path, "rename", cross_device):
            with patch("project.shutil.copy2", side_effect=OSError("Interrupted copy")):
                with self.assertRaisesRegex(OSError, "Interrupted copy"):
                    reports.prepare(self.repo, "Migration test")
            self.assertTrue(original.is_file())
            self.assertFalse((self.new / "settings.json").exists())
            result = reports.prepare(self.repo, "Migration test")

        self.assertTrue(Path(result["directory"]).is_dir())
        self.assertEqual((self.new / "settings.json").read_text(), '{"remind": false}\n')
        self.assertTrue(original.exists())
        self.assertEqual(list(self.new.glob(".migration-*")), [])

    def test_journal_append_during_copy_survives_migration_and_retry(self):
        journal = Path("tasks") / slug("main") / f"{date.today().isoformat()}.jsonl"
        source = self.write(self.old / journal, '{"prompt":"before copy"}\n')
        original_copy2 = shutil.copy2

        def append_during_copy(path, destination):
            original_copy2(path, destination)
            with path.open("a", encoding="utf-8") as stream:
                stream.write('{"prompt":"during copy"}\n')

        with patch("project.shutil.copy2", side_effect=append_during_copy):
            project.migrate(self.repo)
        self.assertFalse((self.new / journal).exists())
        self.assertEqual([item["prompt"] for item in tasks.recent(self.repo)], ["during copy", "before copy"])

        project.migrate(self.repo)
        self.assertEqual((self.new / journal).read_text(), source.read_text())
        with source.open("a", encoding="utf-8") as stream:
            stream.write('{"prompt":"late legacy append"}\n')
        self.assertEqual({item["prompt"] for item in tasks.recent(self.repo)},
                         {"before copy", "during copy", "late legacy append"})

    def test_colliding_task_reports_keep_their_artifacts_together(self):
        today = date.today().isoformat()
        branch = Path("reports") / slug("main")
        task = f"shared-title-{today}"
        other = f"other-title-{today}"
        self.write(self.old / branch / task / "report.md", "Legacy report\n")
        self.write(self.old / branch / task / "summary.json", '{"rounds":[{"round":7}]}\n')
        self.write(self.old / branch / task / "evidence" / "legacy.json", "{}\n")
        self.write(self.new / branch / task / "report.md", "Current report\n")
        self.write(self.new / branch / task / "evidence" / "current.json", "{}\n")
        self.write(self.old / branch / other / "report.md", "Unrelated report\n")

        result = self.entry_json("reports", "--project", str(self.repo), "--task", task)
        self.assertEqual(Path(result["report"]).read_text(), "Current report\n")
        self.assertFalse(Path(result["summary"]).exists())
        self.assertFalse((self.new / branch / task / "evidence" / "legacy.json").exists())
        self.assertTrue((self.old / branch / task / "summary.json").is_file())
        self.assertTrue((self.old / branch / task / "evidence" / "legacy.json").is_file())
        self.assertEqual((self.new / branch / other / "report.md").read_text(), "Unrelated report\n")

    def test_colliding_branch_level_report_keeps_its_own_summary(self):
        branch = Path("reports") / slug("main")
        self.write(self.old / branch / "report.md", "Old branch report\n")
        self.write(self.old / branch / "summary.json", '{"rounds":[{"round":7}]}\n')
        self.write(self.new / branch / "report.md", "New branch report\n")

        project.migrate(self.repo)

        self.assertTrue((self.old / branch / "summary.json").is_file())
        self.assertFalse((self.new / branch / "summary.json").exists())

    def test_branch_level_report_resumes_by_id_alongside_dated_tasks(self):
        branch_id = slug("main")
        branch = Path("reports") / branch_id
        task = f"new-task-{date.today().isoformat()}"
        evidence = self.write(self.old / branch / "evidence" / "qa.json", "{}\n")
        report = self.write(self.old / branch / "report.md", f"[QA](<{evidence.as_posix()}>)\n")
        self.write(self.old / branch / "summary.json", '{"rounds":[{"round":7}]}\n')
        current = self.write(self.new / branch / task / "report.md", "Current report\n")

        preview = reports.prepare(self.repo, branch_id, dry_run=True)
        self.assertEqual(Path(preview["report"]), report)
        self.assertEqual(preview["task_id"], branch_id)
        result = reports.prepare(self.repo, branch_id)
        resumed = Path(result["directory"])
        self.assertEqual(result["task_id"], branch_id)
        self.assertTrue(resumed.is_relative_to(self.new / branch))
        self.assertEqual(Path(result["report"]).read_text(), f"[QA](<{(resumed / 'evidence/qa.json').as_posix()}>)\n")
        self.assertEqual((resumed / "evidence/qa.json").read_text(), "{}\n")
        self.assertEqual(Path(reports.prepare(self.repo)["report"]), current)
        self.assertEqual({item["task_id"]: item["directory"] for item in reports.all_tasks(self.repo)},
                         {branch_id: resumed, task: current.parent})

        summary = self.entry_json("summary", "--project", str(self.repo), "--task", branch_id,
                                  "--round", "8", "--verdict", "PARTIAL CHECK COMPLETE")
        self.assertEqual(Path(summary["file"]), resumed / "summary.json")
        rounds = json.loads(Path(summary["file"]).read_text())["rounds"]
        self.assertEqual([item["round"] for item in rounds], [7, 8])
        self.assertEqual(json.loads((report.parent / "summary.json").read_text())["rounds"], [{"round": 7}])

    def test_retry_cross_filesystem_copy_after_branch_level_report_changes(self):
        branch = Path("reports") / slug("main")
        source = self.write(self.old / branch / "report.md", "Before copy\n")
        rename, copytree = Path.rename, shutil.copytree

        def cross_device(path, target):
            if path == source.parent:
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return rename(path, target)

        def change_after_copy(path, destination, **kwargs):
            copytree(path, destination, **kwargs)
            if path == source.parent:
                source.write_text("During copy\n", encoding="utf-8")

        with patch.object(Path, "rename", cross_device):
            with patch("project.shutil.copytree", side_effect=change_after_copy):
                with self.assertRaisesRegex(ValueError, "still in legacy Ready Check storage"):
                    reports.prepare(self.repo, branch.name)
            self.assertFalse((self.new / branch).exists())
            self.assertEqual(Path(reports.prepare(self.repo, branch.name, dry_run=True)["report"]), source)
            resumed = reports.prepare(self.repo, branch.name)

        self.assertEqual(resumed["task_id"], branch.name)
        self.assertEqual(Path(resumed["report"]), self.new / branch / "report.md")
        self.assertEqual(Path(resumed["report"]).read_text(), "During copy\n")

    def test_concurrent_first_prompts_serialize_exclusion_and_preserve_both_records(self):
        now = datetime.now()
        journal = Path("tasks") / slug("main") / f"{now:%Y-%m-%d}.jsonl"
        self.write(self.old / journal, '{"prompt":"Before upgrade"}\n')
        start = Barrier(2)
        state = local()
        lock = project.migration_lock
        plan = project.git_exclude.plan

        @contextmanager
        def observe_lock(destination):
            with lock(destination):
                state.locked = True
                try:
                    yield
                finally:
                    state.locked = False

        def plan_locked(*args):
            self.assertTrue(getattr(state, "locked", False))
            return plan(*args)

        def record(session):
            start.wait(timeout=10)
            return tasks.record(self.repo, "codex", session, f"Prompt {session}", now=now)

        with patch("project.migration_lock", observe_lock), patch("tasks.migration_lock", observe_lock):
            with patch("project.git_exclude.plan", side_effect=plan_locked):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    self.assertEqual(list(pool.map(record, ("one", "two"))), [self.new / journal] * 2)

        self.assertCountEqual([item["prompt"] for item in tasks.recent(self.repo)],
                              ["Prompt one", "Prompt two", "Before upgrade"])
        lines = (self.repo / ".git/info/exclude").read_text().splitlines()
        self.assertEqual(lines.count("/.ai/ready-check/"), 1)
        self.assertEqual(lines.count("/ai/ready-check/"), 1)

    def test_linked_worktree_upgrade_merges_a_concurrent_exclusion(self):
        self.write(self.old / "rules.md", "- Previous local rule\n")
        linked = self.root / "linked"
        self.git("worktree", "add", "-q", "-b", "linked", str(linked))
        exclude = self.repo / ".git/info/exclude"
        planned, resume = Event(), Event()
        plan = project.git_exclude.plan

        def wait_for_linked(top, paths):
            result = plan(top, paths)
            if top == self.repo:
                planned.set()
                self.assertTrue(resume.wait(timeout=10))
            return result

        with patch("project.git_exclude.plan", side_effect=wait_for_linked), ThreadPoolExecutor() as pool:
            upgrade = pool.submit(tasks.record, self.repo, "codex", "upgrade", "Upgrade prompt")
            try:
                self.assertTrue(planned.wait(timeout=10))
                tasks.record(linked, "codex", "linked", "Linked prompt")
                with exclude.open("ab") as stream:
                    stream.write(b"personal-notes.txt\n")
            finally:
                resume.set()
            self.assertTrue(upgrade.result(timeout=10).is_file())

        self.assertEqual([item["prompt"] for item in tasks.recent(self.repo)], ["Upgrade prompt"])
        self.assertEqual([item["prompt"] for item in tasks.recent(linked)], ["Linked prompt"])
        lines = exclude.read_text().splitlines()
        self.assertEqual(lines.count("/.ai/ready-check/"), 1)
        self.assertEqual(lines.count("/ai/ready-check/"), 1)
        self.assertIn("personal-notes.txt", lines)
        self.assertTrue((self.new / "rules.md").is_file())

    def test_cross_filesystem_report_copy_publishes_a_complete_bundle(self):
        branch = Path("reports") / slug("main")
        task = f"across-volumes-{date.today().isoformat()}"
        folder = branch / task
        evidence = self.write(self.old / folder / "evidence" / "qa.json", "{}\n")
        report = self.write(self.old / folder / "report.md", f"[QA](<{evidence.as_posix()}>)\n")
        rename = Path.rename

        def cross_device(source, target):
            if source == self.old / branch:
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return rename(source, target)

        with patch.object(Path, "rename", cross_device):
            result = reports.prepare(self.repo, task)

        moved = self.new / evidence.relative_to(self.old)
        self.assertEqual(Path(result["report"]).read_text(), f"[QA](<{moved.as_posix()}>)\n")
        self.assertEqual(report.read_text(), f"[QA](<{evidence.as_posix()}>)\n")
        self.assertEqual(moved.read_bytes(), evidence.read_bytes())

    def test_prune_clears_expired_journals_from_both_storage_locations(self):
        now = datetime.now()
        expired = (now - timedelta(days=40)).date().isoformat()
        journal = Path("tasks") / slug("main") / f"{expired}.jsonl"
        old = self.write(self.old / journal, '{"prompt":"expired legacy"}\n')
        new = self.write(self.new / journal, '{"prompt":"expired current"}\n')
        tasks.record(self.repo, "claude", "fixture", "current", now=now)

        self.assertEqual(tasks.prune(self.repo, now=now), 2)
        self.assertFalse(old.exists())
        self.assertFalse(new.exists())
        self.assertEqual([item["prompt"] for item in tasks.recent(self.repo)], ["current"])

    def test_migration_preserves_the_active_native_commit_template(self):
        native = self.write(self.old / "gitmessage.txt", "A native commit template\n")
        relative = native.relative_to(self.repo).as_posix()
        self.git("config", "--local", "commit.template", relative)
        self.write(self.old / "settings.json", "{}\n")

        self.start()

        self.assertTrue(native.is_file())
        self.assertEqual(self.git("config", "--local", "commit.template").strip(), relative)
        self.assertTrue((self.new / "settings.json").is_file())
        result = self.entry_json("template", "commit", "--project", str(self.repo))
        self.assertEqual((result["source"], result["content"]), ("repository", "A native commit template\n"))

    def test_template_resolver_recovers_a_previously_moved_native_template(self):
        self.git("config", "--local", "commit.template", (LEGACY_BASE / "commit.txt").as_posix())
        moved = self.write(self.new / "commit.txt", "Previously moved commit template\n")

        result = self.entry_json("template", "commit", "--project", str(self.repo))

        self.assertEqual(Path(result["path"]), moved)
        self.assertEqual(result["content"], "Previously moved commit template\n")

    def test_interrupted_report_rewrite_retries_after_moving_the_files(self):
        task = f"retry-migration-{date.today().isoformat()}"
        folder = Path("reports") / slug("main") / task
        evidence = self.write(self.old / folder / "checks.json", "{}\n")
        self.write(self.old / folder / "report.md", f"[Checks](<{evidence.as_posix()}>)\n")

        with patch("project.rebase_reports", side_effect=OSError("Interrupted rewrite")):
            with self.assertRaisesRegex(OSError, "Interrupted rewrite"):
                reports.prepare(self.repo, task)
        self.assertTrue((self.new / ".report-migration").is_file())
        result = reports.prepare(self.repo, task)

        moved = self.new / folder / "checks.json"
        self.assertIn(moved.as_posix(), Path(result["report"]).read_text())
        self.assertFalse((self.new / ".report-migration").exists())
        self.assertFalse(self.old.exists())

    @unittest.skipIf(os.name == "nt", "Symlinks need elevated privileges on this Windows runner")
    def test_upgrade_skips_linked_entries_and_preserves_target(self):
        external = self.write(self.root / "external" / "private.json", "External\n")
        self.old.mkdir(parents=True)
        (self.old / "state").symlink_to(external.parent, target_is_directory=True)
        self.write(self.old / "rules.md", "- Local rule\n")
        self.start()
        self.assertTrue((self.old / "state").is_symlink())
        self.assertFalse((self.new / "state").exists())
        self.assertEqual(external.read_text(), "External\n")
        self.assertTrue((self.new / "rules.md").is_file())
