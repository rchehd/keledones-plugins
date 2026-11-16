import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
SPEC = importlib.util.spec_from_file_location("ready_check_mcp_test", PLUGIN / "scripts/mcp.py")
MCP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MCP)


class McpTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-mcp-test.")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve() / "project"
        self.project.mkdir()
        self.data = self.project.parent / "data"

    def test_missing_bundle_never_installs_or_creates_artifacts(self):
        with patch.object(MCP, "data_root", return_value=self.data), self.assertRaisesRegex(ValueError, "setup"):
            MCP.command(self.project, "chromium", False)
        self.assertFalse(self.data.exists())
        self.assertFalse(list(self.project.iterdir()))

    def test_launcher_routes_evidence_and_controls_visibility(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        executable = self.project.parent / "browser"
        executable.touch()
        with patch.object(MCP, "installed", return_value=True), patch.object(MCP, "data_root", return_value=self.data), patch.object(
                MCP, "node_entry", return_value=Path("/installed/cli.js")), patch.object(MCP, "find_command", return_value="node"), patch.object(
                MCP, "execute", return_value=(0, str(executable).encode(), b"")), patch.dict(os.environ, {"PLAYWRIGHT_MCP_HEADLESS": "1"}):
            for headless in (False, True):
                node, args, env, project = MCP.command(self.project, "chromium", headless)
                config = json.loads(Path(args[-1]).read_text())
                self.assertEqual(config["browser"]["launchOptions"]["headless"], headless)
                self.assertTrue(config["browser"]["isolated"])
                self.assertEqual(Path(config["outputDir"]), self.project / MCP.OUTPUT)
                self.assertEqual(MCP.command(self.project, "chromium", headless)[1][-1], args[-1])
                self.assertNotIn("PLAYWRIGHT_MCP_HEADLESS", env)
                self.assertEqual(env["PLAYWRIGHT_BROWSERS_PATH"], str(self.data / "browsers"))
            self.assertEqual(sorted(path.name for path in (self.project / MCP.OUTPUT).iterdir()),
                             ["config-chromium-headed.json", "config-chromium-headless.json"])
            self.assertFalse((self.project / "ai/ready-check/reports").exists())

    def test_outside_git_output_goes_to_data_root(self):
        with patch.object(MCP, "data_root", return_value=self.data):
            self.assertEqual(MCP.output_directory(self.project), self.data / "state/playwright-mcp")
        self.assertFalse((self.project / "ai").exists())

    def test_windows_launch_keeps_stdio_in_a_child_process(self):
        with patch.object(MCP.os, "name", "nt"), patch.object(MCP.os, "chdir") as chdir, patch.object(
                MCP.os, "execvpe") as replace, patch.object(MCP.subprocess, "run") as run:
            run.return_value.returncode = 3
            self.assertEqual(MCP.launch("node", ["node", "mcp.js"], {"A": "1"}, self.project), 3)
        chdir.assert_called_once_with(self.project)
        run.assert_called_once_with(["node", "mcp.js"], env={"A": "1"})
        replace.assert_not_called()

    def test_posix_launch_replaces_the_process(self):
        with patch.object(MCP.os, "name", "posix"), patch.object(MCP.os, "chdir"), patch.object(
                MCP.os, "execvpe") as replace, patch.object(MCP.subprocess, "run") as run:
            MCP.launch("node", ["node", "mcp.js"], {"A": "1"}, self.project)
        replace.assert_called_once_with("node", ["node", "mcp.js"], {"A": "1"})
        run.assert_not_called()

