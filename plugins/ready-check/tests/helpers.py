import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parent.parent
ENTRY = PLUGIN / "scripts/ready-check.py"
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.dont_write_bytecode = True


class RepoTest(unittest.TestCase):
    """A temporary Git repository and a private Ready Check data root."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.data = self.root / "data"
        self.environment = patch.dict(os.environ, {"READY_CHECK_DATA_DIR": str(self.data)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name in ("CLAUDE_PLUGIN_OPTION_RULES", "READY_CHECK_RULES"):
            os.environ.pop(name, None)
        self.git("init", "-q", "-b", "main")
        self.git("commit", "-q", "--allow-empty", "-m", "init")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                              check=True, capture_output=True, text=True).stdout

    def run_entry(self, *args, stdin=None, env=None):
        environment = dict(os.environ, **(env or {}))
        return subprocess.run([sys.executable, "-B", str(ENTRY), *args], input=stdin, capture_output=True, text=True,
                              encoding="utf-8", env=environment)

    def entry_json(self, *args, code=0, **kwargs):
        process = self.run_entry(*args, **kwargs)
        self.assertEqual(process.returncode, code, process.stdout + process.stderr)
        return json.loads(process.stdout) if process.stdout.strip() else None
