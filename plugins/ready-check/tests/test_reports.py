import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parent.parent
ENTRY = PLUGIN / "scripts/ready-check.py"


class ReportsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-reports-test.")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve() / "project"
        self.project.mkdir()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)

    def reports(self, *args, task="Clear delivery note"):
        extra = ["--task", task] if task else []
        process = subprocess.run([sys.executable, "-B", str(ENTRY), "reports", "--project", str(self.project), *extra, *args],
                                 capture_output=True, text=True, encoding="utf-8")
        result = json.loads(process.stdout)
        self.assertEqual(process.returncode, 0 if result["status"] in {"PASS", "PLANNED"} else 2, process.stderr)
        return result

    def commit(self):
        self.git("commit", "-q", "--allow-empty", "-m", "init")

    def test_branch_slug_directory_and_exclusion(self):
        self.git("init", "-q", "-b", "feature/ABC-1@fix")
        self.commit()
        result = self.reports()
        directory = Path(result["directory"])
        self.assertEqual((result["status"], result["branch"]), ("PASS", "feature/ABC-1@fix"))
        self.assertEqual(directory.parent.parent, self.project / ".ai/ready-check/reports")
        self.assertRegex(directory.parent.name, r"^feature-ABC-1-fix-[0-9a-f]{12}$")
        self.assertRegex(directory.name, r"^clear-delivery-note-\d{4}-\d{2}-\d{2}$")
        self.assertEqual(result["task_id"], directory.name)
        self.assertEqual(result["report"], str(directory / "report.md"))
        self.assertTrue(directory.is_dir())
        self.assertFalse((directory / "report.md").exists())
        self.assertIn("/.ai/ready-check/", (self.project / ".git/info/exclude").read_text())
        self.assertEqual(result["git_exclude"]["status"], "PASS")

    def test_similarly_named_branches_keep_separate_resumable_reports(self):
        self.git("init", "-q", "-b", "feature/a")
        self.commit()
        first = self.reports()
        Path(first["report"]).write_text("Answers for feature/a", encoding="utf-8")
        self.git("switch", "-q", "-c", "feature-a")
        second = self.reports()
        self.assertNotEqual(first["directory"], second["directory"])
        self.assertFalse(Path(second["report"]).exists())
        Path(second["report"]).write_text("Answers for feature-a", encoding="utf-8")
        self.git("switch", "-q", "feature/a")
        self.assertEqual(self.reports(task=None)["directory"], first["directory"])
        self.assertEqual(Path(first["report"]).read_text(encoding="utf-8"), "Answers for feature/a")
        self.assertEqual(Path(second["report"]).read_text(encoding="utf-8"), "Answers for feature-a")

    def test_detached_head_uses_short_sha(self):
        self.git("init", "-q")
        self.commit()
        self.git("checkout", "-q", "--detach")
        self.assertRegex(self.reports("--dry-run")["branch"], r"^detached-[0-9a-f]+$")

    def test_dry_run_writes_nothing(self):
        self.git("init", "-q")
        before = (self.project / ".git/info/exclude").read_bytes()
        result = self.reports("--dry-run")
        self.assertEqual((result["status"], result["git_exclude"]["status"]), ("PLANNED", "PLANNED"))
        self.assertFalse((self.project / ".ai").exists())
        self.assertEqual((self.project / ".git/info/exclude").read_bytes(), before)

    def test_non_git_project_creates_directory_and_skips_exclusion(self):
        result = self.reports()
        self.assertEqual((result["status"], result["git_exclude"]["status"]), ("PASS", "SKIPPED"))
        self.assertTrue(Path(result["directory"]).is_dir())

    def test_without_task_and_without_history_asks_for_a_title(self):
        self.git("init", "-q")
        self.commit()
        result = self.reports(task=None)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIn("--task", result["reason"])

    def test_tasks_on_one_branch_get_separate_folders_and_resume_newest(self):
        self.git("init", "-q")
        self.commit()
        first = self.reports(task="Fix cache invalidation")
        second = self.reports(task="Fix cache")
        self.assertNotEqual(first["directory"], second["directory"])
        self.assertEqual(self.reports(task="fix cache invalidation")["directory"], first["directory"])
        Path(first["report"]).write_text("first", encoding="utf-8")
        self.assertEqual(self.reports(task=None)["directory"], first["directory"])

    def test_cyrillic_title_is_transliterated(self):
        self.git("init", "-q")
        self.commit()
        self.assertTrue(self.reports(task="Очистити нотатку")["task_id"].startswith("ochystyty-notatku-"))

    def test_task_names_cannot_escape_the_report_folder(self):
        self.git("init", "-q")
        self.commit()
        for task in ("../../../..", "/tmp", "..\\x"):
            directory = Path(self.reports(task=task)["directory"]).resolve()
            self.assertTrue(directory.is_relative_to((self.project / ".ai/ready-check/reports").resolve()), task)
        self.assertFalse((self.project / "summary.json").exists())

    def test_legacy_branch_report_counts_as_one_task(self):
        self.git("init", "-q")
        self.commit()
        branch_dir = Path(self.reports(task="Seed")["directory"]).parent
        for child in branch_dir.iterdir():
            child.rmdir()
        (branch_dir / "report.md").write_text("old", encoding="utf-8")
        result = self.reports(task=None)
        self.assertEqual((result["task_id"], Path(result["directory"])), (branch_dir.name, branch_dir))
        self.assertEqual(self.reports(task=branch_dir.name)["directory"], result["directory"])

    def test_symlinked_component_is_refused(self):
        target = self.project.parent / "elsewhere"
        target.mkdir()
        try:
            (self.project / ".ai").symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        self.assertEqual(self.reports()["status"], "INCOMPLETE")
        self.assertFalse(list(target.iterdir()))

    def test_project_inside_plugin_is_refused(self):
        self.project = PLUGIN / "tests"
        self.assertEqual(self.reports("--dry-run")["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
