import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from helpers import TempHome
from test_profile import AXES
from test_report import portrait
import digest
import profiles
import report
from sessions import Action, Interaction, Session, Turn, session_from_json, session_to_json
from sources import Builder, claude, codex, cursor
import workflows

STAMP = datetime(2026, 11, 10, tzinfo=timezone.utc)
EDIT = Action("Edit", "edit")
READ = Action("Read", "read")
CHECK = Action("Bash", "test", signature="fixture-check")


def session(*turns, ident="cc-fixture", client="claude", skipped=0):
    return Session(client, ident, "private-project", "/private/path", STAMP, STAMP, list(turns), skipped=skipped)


class WorkflowTest(unittest.TestCase):
    def test_review_orders_decision_and_edits(self):
        review = Turn(STAMP, "Review this diff. No edits.", [READ, EDIT], interaction=[
            Interaction("assistant", 1, "P1 finding at cache.py:16"),
            Interaction("question", 1, "Should I fix the findings?"),
            Interaction("answer", 1, "Go ahead", "Should I fix the findings?"),
        ])
        candidate = session(review)
        case = workflows.analyze(session_from_json(session_to_json(candidate)))
        self.assertEqual(case["steps"], ["review_request", "scope", "read", "findings", "approve", "edit"])
        self.assertEqual(set(case["criteria"].values()), {"observed"})

    def test_missing_answers_and_explicit_review_only_have_distinct_outcomes(self):
        request = "Review this diff. No edits."
        for interaction, skipped, expected in (([], 0, "gap"),
                                               ([Interaction("question", 0, "Should I fix the issue?")], 0, "gap"),
                                               ([], 1, "unknown")):
            with self.subTest(expected=expected, skipped=skipped):
                candidate = session(Turn(STAMP, request, [EDIT], interaction=interaction), skipped=skipped)
                self.assertEqual(workflows.analyze(candidate)["criteria"]["review_permission"], expected)
        replies = [Interaction("question", 0, "Does this fix address the edge case?"),
                   Interaction("answer", 0, "Yes", "Does this fix address the edge case?")]
        self.assertEqual(workflows.analyze(session(Turn(STAMP, request, [EDIT], interaction=replies)))
                         ["criteria"]["review_permission"], "gap")

    def test_repeated_log_reads_do_not_verify_a_fix(self):
        for before, expected in (("cat build.log", "unknown"), ("npm run build", "gap")):
            with self.subTest(before=before):
                builder = Builder()
                builder.start(STAMP, "Fix the export bug.")
                builder.act("Bash", {"command": before})
                builder.act("Edit")
                builder.act("Bash", {"command": "cat build.log"})
                builder.outcome("completed")
                case = workflows.analyze(session(*builder.turns))
                self.assertEqual(case["criteria"]["fix_recheck"], expected)
                self.assertEqual(case["steps"].count("check"), int(expected == "gap"))

    def test_new_edit_offer_requires_its_own_approval(self):
        for first_edit in ([], [EDIT]):
            for answer, expected in (([], "unknown"), ([Turn(STAMP, "Yes")], "observed")):
                with self.subTest(first_edit=bool(first_edit), answer=bool(answer)):
                    case = workflows.analyze(session(
                        Turn(STAMP, "Review the diff. No edits."),
                        Turn(STAMP, "Fix the blocker in cache.py alone.", first_edit,
                             interaction=[Interaction("question", len(first_edit), "May I edit export.py as well?")]),
                        *answer, Turn(STAMP, "Continue", [EDIT]),
                    ))
                    self.assertEqual(case["criteria"]["review_permission"], expected)

    def test_version_requests_do_not_verify_a_fix(self):
        builder = Builder()
        builder.start(STAMP, "Fix the export bug.")
        builder.act("Bash", {"command": "pytest --version"})
        builder.act("Edit")
        builder.act("Bash", {"command": "pytest --version"})
        builder.outcome("completed")
        case = workflows.analyze(session(*builder.turns))
        self.assertEqual(case["criteria"]["fix_recheck"], "unknown")
        self.assertNotIn("check", case["steps"])

    def test_chat_only_review_describes_user_side_and_leaves_agent_unknown(self):
        candidate = session(Turn(STAMP, "Find blockers only"), client="chatgpt")
        criteria = workflows.analyze(candidate)["criteria"]
        self.assertEqual(criteria, dict(review_scope="observed", review_evidence="unknown", review_permission="unknown"))

    def test_fix_requires_same_check_after_final_edit(self):
        request = "Fix the export bug. An empty export should still include the header."
        response = [Interaction("assistant", 1, "Root cause is the early return in export.py:21")]
        for actions, expected in (([READ, CHECK, EDIT, CHECK], "observed"),
                                  ([READ, CHECK, EDIT, CHECK, EDIT], "gap"),
                                  ([READ, CHECK, EDIT, Action("Bash", "test", signature="different")], "unknown")):
            with self.subTest(expected=expected):
                candidate = session(Turn(STAMP, request, actions, "completed", interaction=response))
                criteria = workflows.analyze(candidate)["criteria"]
                self.assertEqual(criteria, dict(fix_expected="observed", fix_cause="observed", fix_recheck=expected))

    def test_ukrainian_review_scope_correction_and_mixed_session(self):
        opening = Turn(STAMP, "Зроби рев’ю перед комітом")
        redirect = Turn(STAMP, "Я просив тільки блокери.")
        grouped = workflows.analyze(session(opening, redirect))
        self.assertEqual(grouped["steps"], ["review_request", "redirect"])
        self.assertEqual(grouped["criteria"]["review_scope"], "gap")
        self.assertEqual(workflows.analyze(session(opening, Turn(STAMP, "Інша задача. Виправ роутер.")))["kind"], "mixed")


class AdapterWorkflowTest(unittest.TestCase):
    def test_permission_uses_the_current_question_identity(self):
        for transport in ("tool", "desktop"):
            for reply_to, expected in (("q1", "gap"), ("q2", "observed")):
                with self.subTest(transport=transport, reply_to=reply_to):
                    builder = Builder()
                    builder.start(STAMP, "Review the diff. No edits.")
                    question = "Should I fix the current finding?"
                    options = {"questions": [{"id": "fix", "question": question}]}
                    for call_id in ("q1", "q2"):
                        builder.act("request_user_input_async", options, call_id)
                    if transport == "tool":
                        builder.tool_answer(reply_to, {"answers": {"fix": {"answers": ["Yes"]}}})
                    else:
                        key = json.dumps(["request_user_input_async", reply_to, 0])
                        reply = {"questionItemId": key, "question": question, "answer": "Yes"}
                        builder.menu_reply(f"<send_user_message_question_reply>{json.dumps([reply])}"
                                           "</send_user_message_question_reply>")
                    builder.act("apply_patch")
                    case = workflows.analyze(session(*builder.turns))
                    self.assertEqual(case["criteria"]["review_permission"], expected)

    def test_ambiguous_plain_yes_does_not_authorize_edits(self):
        for reply in ("Should I fix the finding?\nWould you like the PR summary?",
                      "Should I fix the finding, or only report it?",
                      "Should I fix the cache bug? Should I also edit the exporter?",
                      f"Should I fix the finding after {('a long analysis ' * 15)} or only report it?"):
            with self.subTest(reply=reply):
                builder = Builder()
                builder.start(STAMP, "Review the diff. No edits.")
                builder.visible("assistant", reply)
                builder.start(STAMP, "Yes")
                builder.act("apply_patch")
                case = workflows.analyze(session(*builder.turns))
                self.assertEqual(case["criteria"]["review_permission"], "gap")
                self.assertNotIn("approve", case["steps"])

    def test_codex_repeat_check_includes_the_working_directory(self):
        def record(kind, payload):
            return {"type": kind, "timestamp": STAMP.isoformat(), "payload": payload}

        def call(name, arguments):
            return record("response_item", {"type": "function_call", "name": name, "arguments": json.dumps(arguments)})

        with TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            for after, expected in (("backend", "unknown"), ("frontend", "observed"), (None, "observed")):
                with self.subTest(after=after):
                    repeat = {"cmd": "npm test"}
                    if after:
                        repeat["workdir"] = f"/fixture/{after}"
                    rows = [
                        record("session_meta", {"cwd": "/fixture"}),
                        record("event_msg", {"type": "user_message", "message": "Fix the export bug."}),
                        call("exec_command", {"cmd": "npm test", "workdir": "frontend"}),
                        call("apply_patch", {"target_file": "export.ts"}),
                        record("turn_context", {"cwd": "/fixture/frontend"}),
                        call("exec_command", repeat),
                        record("event_msg", {"type": "task_complete"}),
                    ]
                    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
                    case = workflows.analyze(codex.read(path))
                    self.assertEqual(case["criteria"]["fix_recheck"], expected)

    def test_assistant_message_retains_finding_and_permission_question(self):
        finding = ("P1 finding at export.py:21. The empty export omits its header, so downstream consumers "
                   "cannot infer the column layout. password=fixture-secret")
        for separator, offer in (("\n", "Should I fix the finding?"),
                                 (" ", "Should I go ahead and fix the finding?"),
                                 ("\n", "Чи можу я також виправити цей блокер?")):
            with self.subTest(offer=offer):
                builder = Builder()
                builder.start(STAMP, "Review this diff. No edits.")
                builder.act("Read")
                builder.visible("assistant", finding + separator + offer)
                builder.start(STAMP, "Yes")
                builder.act("Edit")
                candidate = session(*builder.turns)
                case = workflows.analyze(candidate)
                self.assertEqual(case["steps"], ["review_request", "scope", "read", "findings", "approve", "edit"])
                self.assertEqual(case["criteria"]["review_permission"], "observed")
                self.assertEqual(case["criteria"]["review_evidence"], "observed")
                self.assertNotIn("fixture-secret", json.dumps(session_to_json(candidate)))

    def test_visible_review_messages_and_menu_answers(self):
        request = "Review the diff. No edits."
        question = "Should I fix the findings?"
        finding = "P1 finding at cache.py:16. password=fixture-secret"
        questions = {"questions": [{"id": "fix", "question": question, "options": [{"id": "y", "label": "Yes"}]}]}
        blocks = lambda items: {"content": items}
        text = lambda value: {"type": "text", "text": value}
        stamp = STAMP.isoformat()
        message = lambda value: {"type": "message", "role": "assistant", "content": [text(value)]}
        call = lambda name, args: {"type": "function_call", "call_id": "q" if args else "edit",
                                  "name": name, "arguments": json.dumps(args)}
        cases = [
            (claude, [
                {"type": "user", "message": blocks([text(request)])},
                {"type": "assistant", "message": blocks([text(finding),
                    {"type": "tool_use", "id": "q", "name": "AskUserQuestion", "input": questions}])},
                {"type": "user", "message": blocks([{"type": "tool_result", "tool_use_id": "q",
                    "content": f'Your questions have been answered: "{question}"="Yes".'}])},
                {"type": "assistant", "message": blocks([{"type": "tool_use", "name": "Edit"}])},
            ]),
            (codex, [
                {"type": "event_msg", "payload": {"type": "user_message", "message": request}},
                {"type": "response_item", "payload": message(finding)},
                {"type": "response_item", "payload": call("request_user_input", questions)},
                {"type": "event_msg", "payload": {"type": "user_message", "message":
                    "<send_user_message_question_reply>" + json.dumps([{"question": question, "answer": "Yes"}])
                    + "</send_user_message_question_reply>"}},
                {"type": "response_item", "payload": call("apply_patch", {})},
            ]),
            (cursor, [
                {"role": "user", "message": blocks([text(request)])},
                {"role": "assistant", "message": blocks([text(finding),
                    {"type": "tool_use", "id": "q", "name": "AskQuestion", "input": questions}])},
                {"role": "user", "message": blocks([{"type": "tool_result", "tool_use_id": "q", "content":
                    json.dumps({"outcome": {"answers": [{"questionId": "fix", "selectedOptionIds": ["y"]}]}})}])},
                {"role": "assistant", "message": blocks([{"type": "tool_use", "name": "Edit"}])},
            ]),
        ]
        with TemporaryDirectory() as temporary:
            for adapter, rows in cases:
                with self.subTest(client=adapter.CLIENT):
                    path = Path(temporary) / adapter.CLIENT / "agent-transcripts" / "session" / "log.jsonl"
                    path.parent.mkdir(parents=True)
                    path.write_text("\n".join(json.dumps({"timestamp": stamp, **row}) for row in rows), encoding="utf-8")
                    candidate = adapter.read(path)
                    self.assertEqual(len(candidate.turns), 1)
                    result = workflows.analyze(candidate)
                    self.assertEqual(set(result["criteria"].values()), {"observed"})
                    saved = json.dumps(session_to_json(candidate))
                    self.assertNotIn("fixture-secret", saved)
                    self.assertIn("<secret>", saved)


class WorkflowReportTest(unittest.TestCase):
    def test_deterministic_card_metrics_and_support_validation(self):
        candidate = session(Turn(STAMP, "Review the diff. No edits.", [READ, EDIT],
                                 interaction=[Interaction("assistant", 1, "P1 finding at app.py:2 <script>")]))
        with TempHome(), patch("digest.load", return_value=([candidate], [])):
            profiles.set_axes(AXES, "fixture", "developer")
            data = digest.build("month", date(2026, 11, 16))
            quiet = digest.build("month", date(2026, 11, 16), metrics_only=True)
            self.assertEqual(data["workflow"], quiet["workflow"])
            private = json.dumps(quiet)
            for value in (candidate.id, candidate.project, candidate.path, "<script>", "app.py"):
                self.assertNotIn(value, private)
            finding = {"title": "Scope followed", "detail": "Fixture", "tip": "Keep it", "cause": "Explicit scope",
                       "criterion": "review_scope", "evidence": [candidate.id]}
            output = portrait(data, strengths=[finding], growth=[])
            self.assertEqual(report.validate(output, data, profiles.read()), [])
            page = report.render_html(data, output, profiles.read(), None)
            self.assertIn("How you work with agents", page)
            self.assertIn('class="workflow-step workflow-step-agent"', page)
            self.assertIn('<span class="workflow-actor">Agent</span><span>Edit</span>', page)
            self.assertIn('<h4>Criteria</h4>', page)
            self.assertIn('<summary>Recorded scenarios</summary>', page)
            self.assertIn('<dt>Recorded gap</dt><dd>1</dd>', page)
            self.assertIn('<details class="workflow-details">', page)
            self.assertIn('<div class="grid report-stats">', page)
            self.assertLess(page.index('id="profile-radar"'), page.index('id="workflow"'))
            self.assertIn("P1 finding at app.py:2 &lt;script&gt;", page)
            finding["criterion"] = "review_permission"
            self.assertTrue(any("criterion" in error for error in report.validate(output, data, profiles.read())))
