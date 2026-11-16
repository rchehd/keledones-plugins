import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import PLUGIN, RepoTest

STANDARD = {"SessionStart": "session-start", "UserPromptSubmit": "prompt", "Stop": "stop"}
CLIENTS = {
    "claude": ("hooks/hooks.json", "CLAUDE_PLUGIN_ROOT", STANDARD),
    "codex": ("hooks/codex-hooks.json", "PLUGIN_ROOT", STANDARD),
    "cursor": ("hooks/cursor-hooks.json", "CURSOR_PLUGIN_ROOT", {"sessionStart": "session-start", "beforeSubmitPrompt": "prompt"}),
}


def registered(client):
    config = json.loads((PLUGIN / CLIENTS[client][0]).read_text(encoding="utf-8"))
    found = {}

    for event, groups in config["hooks"].items():
        entries = groups if client == "cursor" else [hook for group in groups for hook in group["hooks"]]
        found[event] = [entry["command"] for entry in entries]

    return found


@unittest.skipIf(os.name == "nt" or not shutil.which("sh"), "Registered hook commands are run through a POSIX shell")
class RegisteredHookTest(RepoTest):
    """Runs the hook commands exactly as each client registers them."""

    def setUp(self):
        super().setUp()
        self.plugin = self.root / "plugin with space"
        self.plugin.symlink_to(PLUGIN, target_is_directory=True)

    def run_hook(self, client, event, payload, path=None):
        variable = CLIENTS[client][1]
        environment = {k: v for k, v in os.environ.items() if k not in {c[1] for c in CLIENTS.values()}}
        environment[variable] = str(self.plugin)

        if path:
            environment["PATH"] = path
        outputs = []

        for command in registered(client)[event]:
            process = subprocess.run(["sh", "-c", command], input=json.dumps(payload), capture_output=True, text=True,
                                     encoding="utf-8", env=environment, cwd=self.repo, timeout=30)
            self.assertEqual(process.returncode, 0, f"{client} {event}: {process.stderr}")
            outputs.append(json.loads(process.stdout) if process.stdout.strip() else None)

        return outputs[0] if len(outputs) == 1 else outputs

    def payload(self, client, **extra):
        return dict(cwd=str(self.repo), session_id=client, workspace_roots=[str(self.repo)], **extra)

    def records(self):
        return [json.loads(line)["prompt"] for path in (self.repo / "ai/ready-check/tasks").glob("*/*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]

    def test_each_client_registers_every_event_with_its_own_root(self):
        for client, (_, variable, events) in CLIENTS.items():
            commands = registered(client)
            self.assertEqual(set(commands), set(events), client)

            for event, action in events.items():
                self.assertEqual(len(commands[event]), 1, f"{client} {event}")
                command = commands[event][0]
                self.assertIn(f"hook {action} --client {client}", command)
                self.assertIn('"${' + variable + '}/scripts/ready-check.py"', command)
                self.assertEqual([part.split()[0] for part in command.split(" || ")], ["python3", "python", "py"])

                for other in {c[1] for c in CLIENTS.values()} - {variable}:
                    self.assertNotIn("${" + other + "}", command)

    def test_session_start_injects_the_rule_in_each_client_format(self):
        for client in CLIENTS:
            output = self.run_hook(client, "sessionStart" if client == "cursor" else "SessionStart", self.payload(client))
            text = output["additional_context"] if client == "cursor" else output["hookSpecificOutput"]["additionalContext"]

            if client != "cursor":
                self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
            self.assertIn("Ready Check is enabled", text)
            self.assertIn("check before push", text)

    def test_prompt_is_recorded_in_each_client(self):
        for client in CLIENTS:
            output = self.run_hook(client, "beforeSubmitPrompt" if client == "cursor" else "UserPromptSubmit",
                                   self.payload(client, prompt=f"Task from {client}"))
            self.assertEqual(output, {"continue": True} if client == "cursor" else None)

        self.assertEqual(sorted(self.records()), ["Task from claude", "Task from codex", "Task from cursor"])

    def test_stop_reminds_in_claude_and_blocks_with_a_reason_in_codex(self):
        for client in ("claude", "codex"):
            self.run_hook(client, "SessionStart", self.payload(client))

        (self.repo / "a.php").write_text("<?php\n")
        claude = self.run_hook("claude", "Stop", self.payload("claude"))
        codex = self.run_hook("codex", "Stop", self.payload("codex"))
        self.assertEqual(claude["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertIn("Ready Check", claude["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(codex["decision"], "block")
        self.assertIn("Ready Check", codex["reason"])

    def test_fallback_interpreter_runs_when_python3_fails(self):
        folder = self.root / "bin"
        folder.mkdir()
        (folder / "python3").write_text("#!/bin/sh\nexit 127\n")
        (folder / "python").symlink_to(sys.executable)

        for name in ("git", "sh"):
            (folder / name).symlink_to(shutil.which(name))
        (folder / "python3").chmod(0o755)
        output = self.run_hook("cursor", "beforeSubmitPrompt", self.payload("cursor", prompt="Fallback task"), path=str(folder))
        self.assertEqual(output, {"continue": True})
        self.assertEqual(self.records(), ["Fallback task"])


if __name__ == "__main__":
    unittest.main()
