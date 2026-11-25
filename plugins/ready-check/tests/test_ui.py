import base64
import json
import subprocess
import sys
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.parse import quote


PLUGIN = Path(__file__).resolve().parent.parent
ENTRY = PLUGIN / "scripts/ready-check.py"
sys.path.insert(0, str(PLUGIN / "scripts"))
import git_exclude
from reports import prepare
from reflect_collect import view_feedback
from setup import enable_phpstorm
from ui import LocalView, html
from ui_state import View, reviewed_source


class InteractiveViewTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-ui-test.")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        subprocess.run(["git", "init", "-b", "main"], cwd=self.project, capture_output=True, check=True)
        self.report = prepare(self.project, "interactive views")
        self.directory = Path(self.report["directory"])
        self.task = self.report["task_id"]
        self.report_file = self.directory / "report.md"
        self.report_revisions()

    def report_revisions(self, requirements=1, plan=1, round_number=1):
        self.report_file.write_text(f"# Ready Check\n\nRound: {round_number}\nRequirements revision: {requirements}\nQA plan revision: {plan}\n",
                                    encoding="utf-8")

    def prepare(self, kind, data):
        input_path = self.directory / "input.json"
        input_path.write_text(json.dumps(data), encoding="utf-8")
        view = View(self.project, self.task, kind)
        return view, view.prepare(input_path.name)

    def plan(self, revision=1):
        return dict(round=1, qa_plan_revision=revision, requirements_revision=1,
                    scenarios=[dict(id="QA-001", kind="browser", category="user-flow", required=True,
                                    recording="Retain the clip", recording_required=True,
                                    environment="Local test tenant", preconditions=["Load a disposable fixture"],
                                    execution="Background Chromium", test_data=["Create a record"],
                                    cleanup="Remove the fixture", recording_scope="Keep only the changed interaction"),
                               dict(id="QA-002", required=False)])

    def test_plan_requires_current_revision_required_cases_and_explicit_recording(self):
        view, snapshot = self.prepare("qa-plan", self.plan())
        revision = snapshot["revision"]
        self.assertEqual(snapshot["data"]["scenarios"][0], self.plan()["scenarios"][0])
        self.assertIsNone(view.decision())
        with self.assertRaisesRegex(ValueError, "required scenario"):
            view.submit(dict(action="approve", revision=revision, selected=["QA-002"], recordings=[]))
        with self.assertRaisesRegex(ValueError, "mandatory recording"):
            view.submit(dict(action="approve", revision=revision, selected=["QA-001"], recordings=[]))
        approval = dict(action="approve", revision=revision, selected=["QA-001"], recordings=["QA-001"])
        self.assertEqual(view.submit(approval), view.submit(approval))
        self.assertEqual(view.decision()["qa_plan_revision"], 1)
        with self.assertRaisesRegex(ValueError, "already exists"):
            view.submit(dict(action="cancel", revision=revision))
        self.report_revisions(plan=2)
        self.prepare("qa-plan", self.plan(2))
        self.assertIsNone(view.decision())
        with self.assertRaisesRegex(ValueError, "out of date"):
            view.submit(approval)

    def test_plan_checks_report_revisions_before_preparing_submitting_and_reading(self):
        view, snapshot = self.prepare("qa-plan", self.plan())
        approval = dict(action="approve", revision=snapshot["revision"], selected=["QA-001"], recordings=["QA-001"])
        view.submit(approval)
        for requirements, plan, label in ((2, 1, "Requirements revision"), (1, 2, "QA plan revision")):
            with self.subTest(label=label):
                self.report_revisions(requirements, plan)
                with self.assertRaisesRegex(ValueError, label + " changed"):
                    view.submit(approval)
                with self.assertRaisesRegex(ValueError, label + " changed"):
                    view.decision()
                with self.assertRaisesRegex(ValueError, label + " changed"):
                    self.prepare("qa-plan", self.plan())

    def test_review_keeps_explicit_row_reasons(self):
        payload = dict(round=2, requirements_revision=1, findings=[dict(id="F-001")],
                       reviewed_source=reviewed_source(self.project))
        view, snapshot = self.prepare("review", payload)
        initial = dict(action="triage", revision=snapshot["revision"])
        with self.assertRaises(ValueError):
            view.submit(dict(initial, rows=[dict(id="F-001", action="accept-risk")]))
        result = view.submit(dict(initial, rows=[dict(id="F-001", action="accept-risk", reason="Accepted in scope")]))
        self.assertEqual(result["rows"], [dict(id="F-001", action="accept-risk", reason="Accepted in scope")])
        self.assertEqual(view.decision(), result)
        self.prepare("review", dict(payload, round=3))
        self.assertIsNone(view.decision())
        self.assertEqual(list(view_feedback(self.directory)), [dict(result["rows"][0], round=2)])

    def test_review_decision_requires_the_reviewed_source_at_submit_and_read(self):
        source = self.project / "demo.php"
        source.write_text("<?php echo 1;", encoding="utf-8")
        payload = dict(round=1, requirements_revision=1, findings=[dict(id="F-001", file="demo.php")],
                       reviewed_source=reviewed_source(self.project))
        view, snapshot = self.prepare("review", payload)
        request = dict(action="triage", revision=snapshot["revision"], rows=[dict(id="F-001", action="fix")])
        source.write_text("<?php echo 2;", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "review source snapshot is stale"):
            view.submit(request)
        source.write_text("<?php echo 1;", encoding="utf-8")
        self.assertEqual(view.submit(request)["reviewed_source"], snapshot["data"]["reviewed_source"])
        source.write_text("<?php echo 3;", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "review source snapshot is stale"):
            view.decision()
        _, refreshed = self.prepare("review", dict(payload, reviewed_source=reviewed_source(self.project)))
        self.assertNotEqual(refreshed["revision"], snapshot["revision"])
        self.assertIsNone(view.decision())

    def test_review_rejects_a_snapshot_that_changed_before_preparation(self):
        source = self.project / "demo.php"
        source.write_text("<?php echo 1;", encoding="utf-8")
        command = [sys.executable, str(ENTRY), "ui", "snapshot", "--project", str(self.project), "--view", "review"]
        result = json.loads(subprocess.check_output(command))
        self.assertEqual(result["status"], "PASS")
        payload = dict(round=1, requirements_revision=1, findings=[dict(id="F-001", file="demo.php")])
        with self.assertRaisesRegex(ValueError, "captured before inspection"):
            self.prepare("review", payload)
        source.write_text("<?php echo 2;", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "review source snapshot is stale"):
            self.prepare("review", dict(payload, reviewed_source=result["reviewed_source"]))
        self.assertFalse((self.directory / "ui-review.json").exists())
        view, current = self.prepare("review", dict(payload, reviewed_source=reviewed_source(self.project)))
        del current["data"]["reviewed_source"]["schema_version"]
        view.view_file.write_text(json.dumps(current["data"]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "review source snapshot is stale"):
            view.current()

    def test_review_decision_is_invalid_when_only_requirements_change(self):
        payload = dict(round=1, requirements_revision=1, findings=[dict(id="F-001")],
                       reviewed_source=reviewed_source(self.project))
        view, snapshot = self.prepare("review", payload)
        request = dict(action="triage", revision=snapshot["revision"], rows=[dict(id="F-001", action="fix")])
        self.assertEqual(view.submit(request)["requirements_revision"], 1)
        self.report_file.write_text("# Ready Check\n\nRequirements revision: 2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Requirements revision changed"):
            view.submit(request)
        with self.assertRaisesRegex(ValueError, "Requirements revision changed"):
            view.decision()
        with self.assertRaisesRegex(ValueError, "Requirements revision changed"):
            self.prepare("review", payload)
        _, current = self.prepare("review", dict(payload, requirements_revision=2))
        self.assertNotEqual(current["revision"], snapshot["revision"])
        self.assertIsNone(view.decision())

    @unittest.skipIf(sys.platform == "win32", "This case changes POSIX executable permissions")
    def test_review_snapshot_tracks_git_modes_and_is_stable_across_staging(self):
        source = self.project / "build.sh"
        source.write_text("#!/bin/sh\n", encoding="utf-8")
        source.chmod(0o644)
        git = ["git", "-C", str(self.project)]
        subprocess.run([*git, "config", "core.filemode", "true"], check=True)
        before = reviewed_source(self.project)
        subprocess.run([*git, "add", source.name], check=True)
        self.assertEqual(reviewed_source(self.project), before)
        payload = dict(round=1, requirements_revision=1, findings=[dict(id="F-001")], reviewed_source=before)
        view, snapshot = self.prepare("review", payload)
        source.chmod(0o755)
        after = reviewed_source(self.project)
        self.assertNotEqual(before, after)
        with self.assertRaisesRegex(ValueError, "review source snapshot is stale"):
            view.submit(dict(action="triage", revision=snapshot["revision"], rows=[dict(id="F-001", action="fix")]))
        subprocess.run([*git, "add", source.name], check=True)
        self.assertEqual(reviewed_source(self.project), after)

    def test_gallery_accepts_distinct_actions_and_deduplicates_retries(self):
        self.report_revisions(round_number=2)
        view, state = self.prepare("qa-results", dict(round=2, scenarios=[dict(id="QA-001"), dict(id="QA-002")]))
        actions = [
            dict(action="draft", selected=["QA-001"]),
            dict(action="retest", selected=["QA-002"]),
            dict(action="false-positive", selected=["QA-001"], reason="Fixture drift"),
        ]
        for action in [*actions, actions[0]]:
            view.submit(dict(action, revision=state["revision"]))
        self.assertEqual([item["id"] for item in view.decision()["actions"]],
                         ["draft:QA-001", "retest:QA-002", "false-positive:QA-001"])
        self.assertEqual(list(view_feedback(self.directory)),
                         [dict(id="QA-001", action="false-positive", source="QA", reason="Fixture drift", round=2)])

    def test_reflect_reads_project_history_without_a_task_or_decision(self):
        self.report_file.write_text("Round: 2\nVerdict: BLOCKED\n", encoding="utf-8")
        view = View(self.project, None, "reflect", tasks=1, locale="uk")
        state = view.current()
        data = state["data"]
        self.assertEqual(data["title"], "Статистика Ready Check")
        self.assertEqual(data["metrics"][0]["value"], 1)
        self.assertEqual(data["sections"][0]["rows"][0], [self.task, self.task[-10:], 2, "BLOCKED", None])
        self.assertIsNone(view.decision(state))
        with self.assertRaisesRegex(ValueError, "read-only"):
            view.submit(dict(action="approve", revision=state["revision"]))
        following = prepare(self.project, "newer task")
        Path(following["report"]).write_text("Round: 1\nVerdict: READY TO PUSH\n", encoding="utf-8")
        self.assertEqual(view.current(), state)
        latest = View(self.project, None, "reflect", tasks=1, locale="uk").current()
        self.assertEqual(latest["data"]["sections"][0]["rows"][0][0], following["task_id"])

    def test_gallery_cli_returns_saved_actions_after_round_rollover(self):
        scenarios = [dict(id="QA-001"), dict(id="QA-002")]
        view, original = self.prepare("qa-results", dict(round=1, scenarios=scenarios))
        view.submit(dict(action="retest", selected=["QA-001"], revision=original["revision"]))
        view.submit(dict(action="draft", selected=["QA-002"], revision=original["revision"]))
        self.report_revisions(round_number=2)
        _, current = self.prepare("qa-results", dict(round=2, scenarios=scenarios))
        command = [sys.executable, str(ENTRY), "ui", "decision", "--project", str(self.project),
                   "--task", self.task, "--view", "qa-results"]
        result = json.loads(subprocess.check_output(command))
        self.assertEqual(result["status"], "PASS")
        self.assertIsNone(result["decision"])
        previous, = result["previous_decisions"]
        self.assertEqual((previous["round"], previous["revision"]), (1, original["revision"]))
        self.assertEqual([item["id"] for item in previous["actions"]], ["retest:QA-001", "draft:QA-002"])
        view.submit(dict(action="draft", selected=["QA-002"], revision=current["revision"]))
        updated = json.loads(subprocess.check_output(command))
        self.assertEqual(updated["decision"]["revision"], current["revision"])
        self.assertEqual(updated["previous_decisions"], [previous])

    def test_artifacts_require_a_listed_safe_path_within_evidence(self):
        evidence = self.directory / "evidence"
        evidence.mkdir()
        (evidence / "approved.png").write_bytes(b"PNG")
        (evidence / "hidden.png").write_bytes(b"PNG")
        rows = [dict(id="QA-001", artifacts=[dict(path="evidence/approved.png")])]
        view, snapshot = self.prepare("qa-results", dict(round=1, scenarios=rows))
        revision = snapshot["revision"]
        self.assertEqual(view.artifact("evidence/approved.png", revision)[1], "image/png")
        with self.assertRaisesRegex(ValueError, "not listed"):
            view.artifact("evidence/hidden.png", revision)
        rows[0]["artifacts"][0]["path"] = "evidence/../input.json"
        with self.assertRaisesRegex(ValueError, "inside the report"):
            self.prepare("qa-results", dict(round=1, scenarios=rows))

    def test_settings_and_explicit_setup_share_project_preference(self):
        view = View(self.project, None, "settings")
        self.assertFalse(view.current()["data"]["phpstormMcp"])
        command = [sys.executable, str(ENTRY), "setup", "--project", str(self.project), "--component", "phpstorm"]
        subprocess.run([*command, "--dry-run"], capture_output=True, check=True)
        self.assertFalse(view.current()["data"]["phpstormMcp"])
        with patch("ui_state.secrets.token_hex", return_value="-" + "a" * 31):
            requested = view.submit(dict(revision=view.current()["revision"], action="connect-phpstorm"))
        self.assertTrue(requested["data"]["phpstormPending"])
        self.assertFalse(requested["data"]["phpstormMcp"])
        with self.assertRaisesRegex(ValueError, "Use a connection request"):
            view.submit(dict(revision=requested["revision"], action="set", key="phpstormMcp", value=True))
        decision = subprocess.run([sys.executable, str(ENTRY), "ui", "decision", "--project", str(self.project),
                                   "--view", "settings"], capture_output=True, check=True)
        pending = json.loads(decision.stdout)["decision"]
        self.assertEqual(pending["action"], "connect-phpstorm")
        self.assertEqual(pending["request_id"], requested["data"]["phpstormRequestId"])
        result = subprocess.run([*command, f"--phpstorm-request={pending['request_id']}"],
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)["components"][0]["connection"], "UNVERIFIED")
        current = view.current()
        self.assertTrue(current["data"]["phpstormMcp"])
        self.assertIsNone(view.decision())
        updated = view.submit(dict(revision=current["revision"], action="set", key="phpstormMcp", value=False))
        self.assertFalse(updated["data"]["phpstormMcp"])
        requested = view.submit(dict(revision=updated["revision"], action="connect-phpstorm"))
        self.assertRegex(requested["data"]["phpstormRequestId"], r"^[0-9a-f]{32}$")
        view.submit(dict(revision=requested["revision"], action="set", key="phpstormMcp", value=False))
        self.assertIsNone(view.decision())
        old_setup = [*command, "--phpstorm-request", requested["data"]["phpstormRequestId"]]
        aborted = subprocess.run(old_setup, capture_output=True)
        self.assertEqual(aborted.returncode, 2)
        self.assertIn("cancelled or replaced", json.loads(aborted.stdout)["reason"])
        replacement = view.submit(dict(revision=view.current()["revision"], action="connect-phpstorm"))
        self.assertNotEqual(replacement["revision"], requested["revision"])
        self.assertEqual(subprocess.run(old_setup, capture_output=True).returncode, 2)
        self.assertFalse(view.current()["data"]["phpstormMcp"])
        self.assertEqual(view.decision()["request_id"], replacement["data"]["phpstormRequestId"])
        subprocess.run(command, capture_output=True, check=True)
        self.assertTrue(view.current()["data"]["phpstormMcp"])

    def test_cursor_setup_registers_only_an_approved_local_connection(self):
        view = View(self.project, None, "settings")
        config = self.project / ".cursor/mcp.json"
        config.parent.mkdir()
        other = dict(url="https://example.test/mcp")
        config.write_text(json.dumps(dict(mcpServers=dict(other=other))), encoding="utf-8")
        original = config.read_bytes()
        endpoint = "http://127.0.0.1:64442/stream"

        requested = view.submit(dict(revision=view.current()["revision"], action="connect-phpstorm"))
        request_id = requested["data"]["phpstormRequestId"]
        view.submit(dict(revision=requested["revision"], action="set", key="phpstormMcp", value=False))
        with patch("phpstorm_mcp.verified_endpoint", return_value=True):
            with self.assertRaisesRegex(ValueError, "cancelled or replaced"):
                enable_phpstorm(self.project, False, request_id, "cursor", endpoint)
            self.assertEqual(config.read_bytes(), original)
            self.assertFalse(view.current()["data"]["phpstormMcp"])

            pending = view.submit(dict(revision=view.current()["revision"], action="connect-phpstorm"))
            applied = enable_phpstorm(self.project, False, pending["data"]["phpstormRequestId"], "cursor", endpoint)
            repeated = enable_phpstorm(self.project, False, client="cursor", url=endpoint)

        registration = applied["components"][0]["registration"]
        self.assertEqual(registration["status"], "REGISTERED")
        self.assertTrue(registration["restart_required"])
        self.assertEqual(applied["components"][0]["connection"], "UNVERIFIED")
        self.assertEqual(repeated["components"][0]["registration"]["status"], "ALREADY_REGISTERED")
        servers = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(servers, {"other": other, registration["server"]: dict(url=endpoint,
                         headers={"IJ_MCP_SERVER_PROJECT_PATH": "${workspaceFolder}"})})
        subprocess.run(["git", "check-ignore", str(config)], cwd=self.project, capture_output=True, check=True)
        self.assertTrue(view.current()["data"]["phpstormMcp"])
        self.assertIsNone(view.decision())

    def test_cursor_setup_leaves_tracked_config_and_missing_server_alone(self):
        config = self.project / ".cursor/mcp.json"
        config.parent.mkdir()
        config.write_text('{"mcpServers": {}}\n', encoding="utf-8")
        subprocess.run(["git", "add", str(config)], cwd=self.project, capture_output=True, check=True)
        endpoint = "http://127.0.0.1:64442/stream"
        with patch("phpstorm_mcp.verified_endpoint", return_value=True):
            with self.assertRaisesRegex(ValueError, "tracked Cursor MCP config"):
                enable_phpstorm(self.project, False, client="cursor", url=endpoint)
        self.assertEqual(config.read_text(encoding="utf-8"), '{"mcpServers": {}}\n')
        self.assertFalse(View(self.project, None, "settings").current()["data"]["phpstormMcp"])

        with patch("phpstorm_mcp.verified_endpoint", return_value=False):
            result = enable_phpstorm(self.project, False, client="cursor", url=endpoint)["components"][0]
        self.assertEqual(result["registration"]["status"], "SERVER_UNAVAILABLE")
        self.assertEqual(result["connection"], "UNVERIFIED")
        self.assertEqual(config.read_text(encoding="utf-8"), '{"mcpServers": {}}\n')

    def test_cursor_setup_preserves_concurrent_config_edit_and_can_retry(self):
        config = self.project / ".cursor/mcp.json"
        config.parent.mkdir()
        config.write_text('{"mcpServers": {}}\n', encoding="utf-8")
        updated = '{"mcpServers": {"new-server": {"url": "https://example.test/mcp"}}}\n'
        view = View(self.project, None, "settings")
        request = view.submit(dict(revision=view.current()["revision"], action="connect-phpstorm"))
        request_id = request["data"]["phpstormRequestId"]
        apply_exclude = git_exclude.apply

        def save_from_cursor(plan, **kwargs):
            apply_exclude(plan, **kwargs)
            if "/.cursor/mcp.json" in plan["entries"]:
                config.write_text(updated, encoding="utf-8")

        endpoint = "http://127.0.0.1:64442/stream"
        with patch("phpstorm_mcp.verified_endpoint", return_value=True):
            with patch.object(git_exclude, "apply", side_effect=save_from_cursor):
                with self.assertRaisesRegex(ValueError, "File changed during setup"):
                    enable_phpstorm(self.project, False, request_id, "cursor", endpoint)
            self.assertEqual(config.read_text(encoding="utf-8"), updated)
            self.assertFalse(view.current()["data"]["phpstormMcp"])
            self.assertEqual(view.decision()["request_id"], request_id)
            result = enable_phpstorm(self.project, False, request_id, "cursor", endpoint)["components"][0]
        self.assertEqual(result["registration"]["status"], "REGISTERED")
        servers = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(servers["new-server"], {"url": "https://example.test/mcp"})
        self.assertIsNone(view.decision())

    def test_cursor_setup_verifies_unicode_project_with_inspection_only(self):
        endpoint = "http://127.0.0.1:64442/stream"
        for index, tool in enumerate(("lint_files", "get_file_problems")):
            with self.subTest(tool=tool):
                project = self.project / f"Проєкт-{index}"
                project.mkdir()
                subprocess.run(["git", "init", "--quiet"], cwd=project, capture_output=True, check=True)
                (project / "index.php").write_text("<?php\n", encoding="utf-8")
                subprocess.run(["git", "add", "index.php"], cwd=project, capture_output=True, check=True)

                def reply(_port, headers, method, params, request_id=None):
                    self.assertNotIn("IJ_MCP_SERVER_PROJECT_PATH", headers)
                    if method == "initialize":
                        return dict(serverInfo=dict(name="PhpStorm MCP Server"), protocolVersion="2025-03-26")
                    if method == "tools/list":
                        return dict(tools=[dict(name=tool)])
                    if method == "tools/call":
                        self.assertEqual(params["name"], tool)
                        args = params["arguments"]
                        self.assertEqual(args["projectPath"], str(project))
                        self.assertEqual(args.get("files", [args.get("filePath")]), ["index.php"])
                    return {}

                with patch("phpstorm_mcp.rpc", side_effect=reply):
                    result = enable_phpstorm(project, False, client="cursor", url=endpoint)["components"][0]
                registration = result["registration"]
                self.assertEqual(registration["status"], "REGISTERED")
                config = json.loads((project / ".cursor/mcp.json").read_text(encoding="utf-8"))
                self.assertEqual(config["mcpServers"][registration["server"]], {"url": endpoint})

    def test_mcp_exposes_only_the_read_only_qa_view_and_listed_media(self):
        child = subprocess.Popen([sys.executable, str(ENTRY), "ui-mcp"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8")
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.stdin.close)
        self.addCleanup(child.wait, 5)
        self.addCleanup(child.terminate)

        def call(method, params=None, *, error=False):
            child.stdin.write(json.dumps(dict(jsonrpc="2.0", id=1, method=method, params=params or {})) + "\n")
            child.stdin.flush()
            return json.loads(child.stdout.readline())["error" if error else "result"]

        capabilities = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}
        call("initialize", dict(protocolVersion="2025-11-25", capabilities={}))
        self.assertNotIn("_meta", call("tools/list")["tools"][0])
        self.assertEqual(call("resources/templates/list")["resourceTemplates"], [])
        call("initialize", dict(protocolVersion="2025-11-25", capabilities=capabilities))
        show, media, fallback_tool = call("tools/list")["tools"]
        self.assertEqual([show["name"], media["name"], fallback_tool["name"]], ["show_view", "preview_media", "local_view"])
        self.assertEqual(show["inputSchema"]["properties"]["view"]["enum"], ["qa-results"])
        self.assertEqual(media["_meta"]["ui"]["visibility"], ["app"])
        uri = show["_meta"]["ui"]["resourceUri"]
        self.assertEqual(call("resources/read", {"uri": uri})["contents"][0]["text"], html())
        args = dict(project=str(self.project), task=self.task, view="qa-results")
        for kind in ("qa-plan", "review", "settings", "reflect"):
            with self.subTest(kind=kind):
                rejected = call("tools/call", dict(name="show_view", arguments=dict(args, view=kind)))
                self.assertTrue(rejected["isError"])
        evidence = self.directory / "evidence"
        evidence.mkdir()
        (evidence / "image.png").write_bytes(b"PNG")
        (evidence / "clip.webm").write_bytes(b"WEBM")
        (evidence / "after.png").write_bytes(b"AFTER PNG")
        (evidence / "after.webm").write_bytes(b"AFTER WEBM")
        (evidence / "hidden.webm").write_bytes(b"HIDDEN")
        (evidence / "hidden.png").write_bytes(b"HIDDEN PNG")
        (evidence / "large.png").write_bytes(b"x" * 128_001)
        carried = []
        for number in range(3):
            name = f"image-{number}.png"
            (evidence / name).write_bytes(b"y" * 128_000)
            carried.append(f"evidence/{name}")
        paths = [dict(path="evidence/image.png", title="Before screenshot"),
                 dict(path="evidence/after.png", title="After screenshot"),
                 dict(path="evidence/clip.webm", title="Before clip"),
                 dict(path="evidence/after.webm", title="After clip"),
                 dict(path="evidence/large.png", title="Large screenshot"),
                 *(dict(path=name) for name in carried)]
        scenarios = [dict(id="QA-001", kind="browser", category="accessibility", artifacts=paths), dict(id="QA-002")]
        self.prepare("qa-results", dict(round=1, scenarios=scenarios))
        opened = call("tools/call", dict(name="show_view", arguments=args))
        gallery = opened["structuredContent"]
        previews = opened["_meta"]["readyCheckPreviews"]
        self.assertEqual(set(previews), {"evidence/image.png", "evidence/after.png", *carried[:2]})
        self.assertEqual(base64.b64decode(previews["evidence/image.png"]["data"]), b"PNG")
        self.assertNotIn("readyCheckPreviews", gallery)
        self.assertNotIn(previews["evidence/image.png"]["data"], opened["content"][0]["text"])
        self.assertEqual(gallery["data"]["scenarios"][0]["artifacts"], paths)
        self.assertEqual(gallery["data"]["scenarios"][0]["kind"], "browser")
        self.assertEqual(gallery["data"]["scenarios"][0]["category"], "accessibility")
        self.assertNotIn("kind", gallery["data"]["scenarios"][1])
        self.assertNotIn("category", gallery["data"]["scenarios"][1])
        self.assertEqual(gallery["data"]["scenarios"][1]["artifacts"], [])
        self.assertNotIn("decision", gallery)
        handle = gallery["handle"]
        rejected = call("tools/call", dict(name="submit_decision", arguments=dict(handle=handle)))
        self.assertTrue(rejected["isError"])
        preview = dict(name="preview_media", arguments=dict(handle=handle, path="evidence/image.png"))
        self.assertEqual(call("tools/call", preview)["structuredContent"]["mimeType"], "image/png")
        clip = dict(name="preview_media", arguments=dict(handle=handle, path="evidence/clip.webm"))
        video = call("tools/call", clip)["structuredContent"]
        self.assertEqual(video["mimeType"], "video/webm")
        self.assertEqual(base64.b64decode(video["data"]), b"WEBM")
        template, = call("resources/templates/list")["resourceTemplates"]

        def read_video(path, view_handle=handle, *, error=False):
            resource_uri = template["uriTemplate"].format(handle=view_handle, path=quote(path, safe=""))
            return call("resources/read", dict(uri=resource_uri), error=error)

        resource, = read_video("evidence/clip.webm")["contents"]
        self.assertEqual(resource["mimeType"], "video/webm")
        self.assertEqual(base64.b64decode(resource["blob"]), b"WEBM")
        self.assertNotIn(handle, json.dumps(call("resources/list")))
        self.assertEqual(read_video("evidence/clip.webm", "unknown", error=True)["code"], -32602)
        for name in ("evidence/hidden.webm", "../clip.webm", "evidence/image.png"):
            with self.subTest(resource=name):
                self.assertEqual(read_video(name, error=True)["code"], -32602)
        for name, expected in (("after.png", b"AFTER PNG"), ("after.webm", b"AFTER WEBM")):
            asset = call("tools/call", dict(name="preview_media", arguments=dict(handle=handle, path=f"evidence/{name}")))
            self.assertEqual(base64.b64decode(asset["structuredContent"]["data"]), expected)
        hidden = dict(name="preview_media", arguments=dict(handle=handle, path="evidence/hidden.webm"))
        self.assertTrue(call("tools/call", hidden)["isError"])
        with (evidence / "clip.webm").open("ab") as recording:
            recording.truncate(4_000_001)
        self.assertEqual(call("tools/call", clip)["structuredContent"], dict(open_local=True))
        self.assertIn("local report", read_video("evidence/clip.webm", error=True)["message"])
        fallback = dict(name="local_view", arguments=dict(handle=handle))
        if gallery["url"] is not None:
            self.assertRegex(gallery["url"], r"^http://127\.0\.0\.1:\d+/#")
            self.assertEqual(call("tools/call", fallback)["structuredContent"]["url"], gallery["url"])
        self.report_revisions(round_number=2)
        self.assertIn("Round changed", read_video("evidence/after.webm", error=True)["message"])
        for request in (dict(name="show_view", arguments=args), preview, fallback):
            stale = call("tools/call", request)
            self.assertTrue(stale["isError"])
            self.assertIn("Round changed", stale["content"][0]["text"])
        self.prepare("qa-results", dict(round=2, scenarios=[dict(id="QA-001", artifacts=paths)]))
        fresh = call("tools/call", dict(name="show_view", arguments=args))["structuredContent"]
        self.assertEqual(fresh["data"]["round"], 2)
        self.assertEqual(fresh["data"]["scenarios"][0]["artifacts"], paths)
        self.assertIn("out of date", read_video("evidence/after.webm", error=True)["message"])
        current_clip, = read_video("evidence/after.webm", fresh["handle"])["contents"]
        self.assertEqual(base64.b64decode(current_clip["blob"]), b"AFTER WEBM")
        with self.assertRaisesRegex(ValueError, "Round changed"):
            self.prepare("qa-results", dict(round=1, scenarios=[dict(id="QA-002")]))
        current_preview = dict(name="preview_media", arguments=dict(handle=fresh["handle"], path="evidence/after.png"))
        self.assertEqual(base64.b64decode(call("tools/call", current_preview)["structuredContent"]["data"]), b"AFTER PNG")
        for request in (preview, fallback):
            result = call("tools/call", request)
            self.assertTrue(result["isError"])
            self.assertIn("out of date", result["content"][0]["text"])

    def test_loopback_requires_token_identity_and_serves_a_media_range(self):
        evidence = self.directory / "evidence"
        evidence.mkdir()
        (evidence / "screen.png").write_bytes(b"PNG")
        (evidence / "play.webm").write_bytes(b"0123456789")
        rows = [dict(id="QA-001", artifacts=[dict(path="evidence/screen.png"), dict(path="evidence/play.webm")])]
        view, snapshot = self.prepare("qa-results", dict(round=1, scenarios=rows))
        try:
            server = LocalView(view)
        except PermissionError:
            self.skipTest("Loopback sockets are unavailable in this sandbox")
        self.addCleanup(server.server_close)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)

        def get(path, headers=None):
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()

        self.assertEqual(get("/state", {"Host": "unexpected.test"})[0], 403)
        self.assertEqual(get("/state")[0], 404)
        self.assertEqual(get("/state", {"Authorization": "Bearer " + server.token})[0], 200)
        connection.request("GET", "/")
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIn("media-src 'self'", response.getheader("Content-Security-Policy"))
        self.assertIn(b'id="ready-check"', response.read())
        connection.request("POST", "/decision", body=b"{}", headers={"Authorization": "Bearer " + server.token})
        response = connection.getresponse()
        self.assertEqual(response.status, 501)
        response.read()
        access = f"&access={server.token}&revision={snapshot['revision']}"
        self.assertEqual(get("/asset?name=evidence/screen.png" + access), (200, b"PNG"))
        url = "/asset?name=evidence/play.webm" + access
        connection.request("GET", url, headers={"Range": "bytes=2-5"})
        response = connection.getresponse()
        self.assertEqual(response.status, 206)
        self.assertEqual(response.getheader("Content-Type"), "video/webm")
        self.assertEqual(response.getheader("Content-Range"), "bytes 2-5/10")
        self.assertEqual(response.read(), b"2345")
        self.report_revisions(round_number=2)
        for route, headers in (("/state", {"Authorization": "Bearer " + server.token}), (url, {})):
            status, body = get(route, headers)
            self.assertEqual(status, 400)
            self.assertIn("Round changed", json.loads(body)["error"])
        self.prepare("qa-results", dict(round=2, scenarios=rows))
        status, body = get(url)
        self.assertEqual(status, 400)
        self.assertIn("out of date", json.loads(body)["error"])
