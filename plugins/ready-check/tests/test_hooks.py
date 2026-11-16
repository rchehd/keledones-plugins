import json
import sys
import unittest
from io import StringIO
from unittest.mock import patch

from helpers import ENTRY, RepoTest


class HookTest(RepoTest):
    def hook(self, event, client, payload):
        process = self.run_entry("hook", event, "--client", client,
                                 stdin=payload if isinstance(payload, str) else json.dumps(payload))
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout) if process.stdout.strip() else None

    def test_cursor_prompt_is_always_allowed(self):
        for stdin in ("", "not json", "[1, 2]", json.dumps({"prompt": "x", "workspace_roots": [str(self.repo)]})):
            self.assertEqual(self.hook("prompt", "cursor", stdin), {"continue": True})

    def test_prompt_outside_git_writes_nothing(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.assertIsNone(self.hook("prompt", "claude", {"cwd": str(outside), "prompt": "task"}))
        self.assertEqual(list(outside.iterdir()), [])

    def test_prompt_is_recorded_per_branch(self):
        self.hook("prompt", "claude", {"cwd": str(self.repo), "session_id": "s", "prompt": "Add a clear button"})
        records = list((self.repo / "ai/ready-check/tasks").glob("*/*.jsonl"))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text())["prompt"], "Add a clear button")

    def test_session_start_injects_rule_status_and_first_run(self):
        for client, key in (("claude", ("hookSpecificOutput", "additionalContext")), ("cursor", ("additional_context",))):
            output = self.hook("session-start", client, {"cwd": str(self.repo), "session_id": client})
            text = output[key[0]][key[1]] if len(key) == 2 else output[key[0]]
            self.assertIn("ask once in the user's", text)
            self.assertIn("Ready Check browser tools:", text)
            self.assertIn("consent yes", text)

    def test_first_run_names_a_non_php_project_without_php(self):
        (self.repo / "go.mod").write_text("module example.com/app\n\ngo 1.26\n")
        text = self.hook("session-start", "claude", {"cwd": str(self.repo), "session_id": "g"})["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Ready Check detected: Go, local.", text)
        self.assertNotIn("PHP", text)

    def test_stop_reminds_once_per_change_and_respects_checks(self):
        payload = {"cwd": str(self.repo), "session_id": "s"}
        self.hook("session-start", "claude", payload)
        self.assertIsNone(self.hook("stop", "claude", payload))
        (self.repo / "a.php").write_text("<?php\n")
        reminder = self.hook("stop", "claude", payload)
        self.assertEqual(reminder["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertIsNone(self.hook("stop", "claude", payload))
        (self.repo / "a.php").write_text("<?php // changed\n")
        self.assertIsNone(self.hook("stop", "claude", dict(payload, stop_hook_active=True)))
        self.entry_json("mark-checked", "--project", str(self.repo))
        self.assertIsNone(self.hook("stop", "claude", payload))
        (self.repo / "b.php").write_text("<?php\n")
        self.assertIn("ask once", self.hook("stop", "claude", payload)["hookSpecificOutput"]["additionalContext"])

    def test_codex_stop_uses_block_with_reason(self):
        payload = {"cwd": str(self.repo), "session_id": "c"}
        self.hook("session-start", "codex", payload)
        (self.repo / "a.php").write_text("<?php\n")
        output = self.hook("stop", "codex", payload)
        self.assertEqual(output["decision"], "block")
        self.assertIn("Ready Check", output["reason"])

    def test_old_python_never_blocks(self):
        import runpy
        with patch.object(sys, "version_info", (3, 8, 0)), patch.object(sys, "argv", [str(ENTRY), "hook", "prompt", "--client", "cursor"]), \
                patch("sys.stdout", new_callable=StringIO) as output:
            with self.assertRaises(SystemExit) as stop:
                runpy.run_path(str(ENTRY), run_name="__main__")
        self.assertEqual(stop.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue()), {"continue": True})


if __name__ == "__main__":
    unittest.main()
