import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
import git_exclude


def git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


class GitExcludeTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-exclude-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        self.file = self.repo / ".git/info/exclude"

    def run_plan(self, entries, project=None):
        plan = git_exclude.plan(project or self.repo, entries)
        git_exclude.apply(plan)
        return plan

    def test_block_is_created_updated_and_idempotent(self):
        plan = self.run_plan([".ai/ready-check/"])
        self.assertEqual((plan["action"], plan["entries"]), ("update", ["/.ai/ready-check/"]))
        self.assertIn(b"# ready-check:begin\n/.ai/ready-check/\n# ready-check:end\n", self.file.read_bytes())
        self.assertEqual(self.run_plan([".ai/ready-check/"])["action"], "unchanged")
        self.run_plan([".ai/ready-check/", "AGENTS.md"])
        text = self.file.read_text()
        self.assertEqual(text.count("ready-check:begin"), 1)
        self.assertEqual(text.count("/AGENTS.md"), 1)

    def test_union_keeps_existing_block_entries_and_foreign_lines(self):
        self.file.write_bytes(b"*.log\n# ready-check:begin\n/AGENTS.md\n# ready-check:end\nfoo\n")
        self.run_plan([".ai/ready-check/"])
        self.assertEqual(self.file.read_bytes(),
                         b"*.log\n# ready-check:begin\n/AGENTS.md\n/.ai/ready-check/\n# ready-check:end\nfoo\n")

    def test_missing_file_is_created_and_crlf_is_preserved(self):
        self.file.unlink()
        self.assertEqual(git_exclude.plan(self.repo, ["a/"])["action"], "create")
        self.file.write_bytes(b"keep\r\n")
        self.run_plan(["a/"])
        self.assertEqual(self.file.read_bytes(), b"keep\r\n# ready-check:begin\r\n/a/\r\n# ready-check:end\r\n")

    def test_malformed_markers_are_rejected(self):
        self.file.write_bytes(b"# ready-check:begin\n/a\n")
        with self.assertRaises(ValueError):
            git_exclude.plan(self.repo, ["a/"])

    def test_non_git_project_returns_none(self):
        folder = self.root / "plain"
        folder.mkdir()
        self.assertIsNone(git_exclude.plan(folder, ["a/"]))

    def test_nested_project_is_anchored_to_repository_root(self):
        nested = self.repo / "apps/site"
        nested.mkdir(parents=True)
        self.assertEqual(git_exclude.plan(nested, [".ai/ready-check/"])["entries"], ["/apps/site/.ai/ready-check/"])

    def test_worktree_resolves_shared_exclude_file(self):
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init")
        tree = self.root / "tree"
        git(self.repo, "worktree", "add", "-q", str(tree), "-b", "other")
        plan = self.run_plan([".ai/ready-check/"], tree)
        self.assertEqual(plan["path"], self.file)
        self.assertEqual(plan["entries"], ["/.ai/ready-check/"])
        self.assertIn(b"/.ai/ready-check/", self.file.read_bytes())

    def test_change_between_plan_and_apply_is_refused(self):
        plan = git_exclude.plan(self.repo, ["a/"])
        self.file.write_bytes(b"edited\n")
        with self.assertRaises(ValueError):
            git_exclude.apply(plan)
        self.assertEqual(self.file.read_bytes(), b"edited\n")


if __name__ == "__main__":
    unittest.main()
