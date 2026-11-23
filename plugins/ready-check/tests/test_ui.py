import json
import subprocess
import sys
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread


PLUGIN = Path(__file__).resolve().parent.parent
ENTRY = PLUGIN / "scripts/ready-check.py"
sys.path.insert(0, str(PLUGIN / "scripts"))
from reports import prepare
from reflect_collect import view_feedback
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

    def report_revisions(self, requirements=1, plan=1):
        self.report_file.write_text(f"# Ready Check\n\nRequirements revision: {requirements}\nQA plan revision: {plan}\n",
                                    encoding="utf-8")

    def prepare(self, kind, data):
        input_path = self.directory / "input.json"
        input_path.write_text(json.dumps(data), encoding="utf-8")
        view = View(self.project, self.task, kind)
        return view, view.prepare(input_path.name)

    def plan(self, revision=1):
        return dict(round=1, qa_plan_revision=revision, requirements_revision=1,
                    scenarios=[dict(id="QA-001", required=True, recording="Retain the clip", recording_required=True,
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
        result = subprocess.run([*command, "--phpstorm-request", pending["request_id"]],
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)["components"][0]["connection"], "UNVERIFIED")
        current = view.current()
        self.assertTrue(current["data"]["phpstormMcp"])
        self.assertIsNone(view.decision())
        updated = view.submit(dict(revision=current["revision"], action="set", key="phpstormMcp", value=False))
        self.assertFalse(updated["data"]["phpstormMcp"])
        requested = view.submit(dict(revision=updated["revision"], action="connect-phpstorm"))
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

    def test_mcp_exposes_app_resource_and_records_a_view_decision(self):
        self.prepare("qa-plan", self.plan())
        child = subprocess.Popen([sys.executable, str(ENTRY), "ui-mcp"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8")
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.stdin.close)
        self.addCleanup(child.wait, 5)
        self.addCleanup(child.terminate)

        def call(method, params=None):
            child.stdin.write(json.dumps(dict(jsonrpc="2.0", id=1, method=method, params=params or {})) + "\n")
            child.stdin.flush()
            return json.loads(child.stdout.readline())["result"]

        capabilities = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}
        call("initialize", dict(protocolVersion="2025-11-25", capabilities={}))
        self.assertNotIn("_meta", call("tools/list")["tools"][0])
        call("initialize", dict(protocolVersion="2025-11-25", capabilities=capabilities))
        uri = call("tools/list")["tools"][0]["_meta"]["ui"]["resourceUri"]
        self.assertEqual(call("resources/read", {"uri": uri})["contents"][0]["text"], html())
        args = dict(project=str(self.project), task=self.task, view="qa-plan")
        shown = call("tools/call", dict(name="show_view", arguments=args))["structuredContent"]
        accepted = call("tools/call", dict(name="submit_decision", arguments={
            "handle": shown["handle"], "decision": {"revision": shown["revision"], "action": "cancel"},
        }))
        self.assertEqual(accepted["structuredContent"]["action"], "cancel")
        self.assertEqual(View(self.project, self.task, "qa-plan").decision()["action"], "cancel")
        evidence = self.directory / "evidence"
        evidence.mkdir()
        (evidence / "image.png").write_bytes(b"PNG")
        paths = [dict(path="evidence/image.png")]
        self.prepare("qa-results", dict(round=1, scenarios=[dict(id="QA-001", artifacts=paths)]))
        gallery = call("tools/call", dict(name="show_view", arguments=dict(args, view="qa-results")))
        handle = gallery["structuredContent"]["handle"]
        preview = dict(name="preview_image", arguments=dict(handle=handle, path="evidence/image.png"))
        self.assertEqual(call("tools/call", preview)["structuredContent"]["mimeType"], "image/png")
        with (evidence / "image.png").open("ab") as image:
            image.truncate(4_000_001)
        self.assertEqual(call("tools/call", preview)["structuredContent"], dict(open_local=True))
        self.prepare("qa-results", dict(round=2, scenarios=[dict(id="QA-002", artifacts=paths)]))
        fallback = dict(name="local_view", arguments=dict(handle=handle))
        for request in (preview, fallback):
            result = call("tools/call", request)
            self.assertTrue(result["isError"])
            self.assertIn("out of date", result["content"][0]["text"])

    def test_loopback_requires_token_identity_and_serves_a_media_range(self):
        evidence = self.directory / "evidence"
        evidence.mkdir()
        (evidence / "play.webm").write_bytes(b"0123456789")
        rows = [dict(id="QA-001", artifacts=[dict(path="evidence/play.webm")])]
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
        url = f"/asset?name=evidence/play.webm&access={server.token}&revision={snapshot['revision']}"
        self.assertEqual(get(url, {"Range": "bytes=2-5"}), (206, b"2345"))
        self.prepare("qa-results", dict(round=2, scenarios=rows))
        status, body = get(url)
        self.assertEqual(status, 400)
        self.assertIn("out of date", json.loads(body)["error"])
