import unittest
from datetime import date, datetime, timezone

import helpers  # noqa: F401
import sessions
from sessions import Action, Session, Turn, classify, clean_request, window


class CleanRequestTest(unittest.TestCase):
    def test_strips_injected_context(self):
        text = ("<system-reminder>be nice</system-reminder>\n<environment_context>cwd</environment_context>"
                "<INSTRUCTIONS>x</INSTRUCTIONS><user_instructions>y</user_instructions>"
                "<local-command-stdout>out</local-command-stdout><timestamp>Friday</timestamp>"
                "<user_query>\nfix the login form\n</user_query>")
        self.assertEqual(clean_request(text), "fix the login form")

    def test_strips_agents_block(self):
        self.assertEqual(clean_request("# AGENTS.md instructions\n\n<INSTRUCTIONS>rules</INSTRUCTIONS>"), "")

    def test_command_name_becomes_slash_command(self):
        text = "<command-message>review</command-message>\n<command-name>/review</command-name>\n<command-args></command-args>"
        self.assertEqual(clean_request(text), "/review")

    def test_strips_client_context_blocks(self):
        text = ('<artifact-view-context artifact="a">page</artifact-view-context><manually_attached_skills>s'
                '</manually_attached_skills><send_user_message_question_reply>[1]</send_user_message_question_reply>'
                'make it blue')
        self.assertEqual(clean_request(text), "make it blue")
        self.assertEqual(clean_request("<task-notification><task-id>b1</task-id></task-notification>"), "")

    def test_pasted_content_is_replaced(self):
        self.assertEqual(clean_request('look <pasted_content id="1">secret log</pasted_content> here'),
                         "look [pasted text] here")
        self.assertEqual(clean_request('<pasted_content id="2">log</pasted_content id="2">\nwhat now'),
                         "[pasted text]\nwhat now")

    def test_cursor_command_becomes_slash_command(self):
        text = "<cursor_commands>--- Cursor Command: generate-report ---\nlong body\n</cursor_commands>\nfor May"
        self.assertEqual(clean_request(text), "/generate-report\nfor May")

    def test_drops_agent_handoffs(self):
        for text in ("The following is the Codex agent history added since your last turn",
                     "The beginning of the above subagent result is already visible to the user.",
                     "Perform any necessary follow-up actions in response to the subagent."):
            self.assertEqual(clean_request(text), "", text)

    def test_drops_automatic_prompts(self):
        self.assertEqual(clean_request("[Request interrupted by user]"), "")
        self.assertEqual(clean_request("[Request interrupted by user for tool use]"), "")
        self.assertEqual(clean_request("<user_query>Briefly inform the user about the task result and perform any "
                                       "follow-up actions (if needed).</user_query>"), "")
        self.assertEqual(clean_request("<system-reminder>only this</system-reminder>"), "")


class ClassifyTest(unittest.TestCase):
    def kind(self, tool, detail=""):
        return classify(tool, detail).kind

    def test_kinds(self):
        for tool in ("Edit", "Write", "MultiEdit", "apply_patch", "edit_file", "search_replace"):
            self.assertEqual(self.kind(tool), "edit", tool)

        for tool in ("Read", "Grep", "Glob", "read_file", "codebase_search"):
            self.assertEqual(self.kind(tool), "read", tool)

        for tool in ("Bash", "Shell", "exec_command", "exec"):
            self.assertEqual(self.kind(tool, "ls -la"), "shell", tool)
            self.assertEqual(self.kind(tool, "python -m pytest tests"), "test", tool)

        self.assertEqual(self.kind("Bash", "npm run test"), "test")
        self.assertEqual(self.kind("Task"), "subagent")
        self.assertEqual(self.kind("Agent"), "subagent")
        self.assertEqual(self.kind("spawn_agent"), "subagent")

        for tool in ("EnterPlanMode", "ExitPlanMode", "update_plan", "TodoWrite"):
            self.assertEqual(self.kind(tool), "plan", tool)

        self.assertEqual(self.kind("CallDynamicTool"), "mcp")
        self.assertEqual(self.kind("WebSearch"), "other")

    def test_names(self):
        self.assertEqual(classify("Skill", "superpowers:brainstorming"), Action("Skill", "skill", "superpowers:brainstorming"))
        self.assertEqual(classify("mcp__context7__query-docs"), Action("mcp__context7__query-docs", "mcp", "context7"))

    def test_checks_are_commands_not_words_in_arguments(self):
        for command in ("cat build.log", 'rg "pytest"', "echo npm run lint", "git show build",
                        'printf "%s" "x && pytest"', "echo escaped\\; pytest", "echo x # check; pytest"):
            with self.subTest(command=command):
                self.assertEqual(self.kind("Bash", command), "shell")

        for command in ("pytest tests", "python3 -B -m unittest", "npm run lint", "go test ./...",
                        "cargo build", 'cd "build folder" && rtk proxy python -m pytest',
                        r".\.venv\Scripts\python.exe -m pytest", "pnpm exec eslint ."):
            with self.subTest(command=command):
                self.assertEqual(self.kind("Bash", command), "test")

    def test_runner_options_distinguish_checks_from_information_commands(self):
        for command in ("pytest --version", "python -m pytest -V", "ruff check --help",
                        "pnpm exec eslint --version", "pytest --collect-only", "tsc --showConfig",
                        "make -C frontend --just-print test", "npm --prefix frontend run lint --help",
                        "pytest --fixtures", "go test -list .", "go test -list=.", "jest --listTests", "jest --list-tests",
                        "ruff rule E501", "ruff check --show-settings", "ruff format .",
                        "cat <<EOF\npytest\nEOF"):
            with self.subTest(command=command):
                self.assertEqual(self.kind("Bash", command), "shell")

        for command in ("npm --prefix frontend run lint", 'npm --prefix="front end" run lint',
                        "make -C frontend test", "make -Cfrontend test", "pnpm --filter @scope/app test",
                        "go -C backend test ./...", "pytest -n 2", "ruff check .", "ruff format --check .",
                        "pytest && cat <<EOF\nFinished\nEOF"):
            with self.subTest(command=command):
                self.assertEqual(self.kind("Bash", command), "test")


class WindowTest(unittest.TestCase):
    def test_month(self):
        self.assertEqual(window("month", date(2026, 11, 16)), {
            "start": date(2026, 10, 18), "end": date(2026, 11, 16),
            "previous": {"start": date(2026, 9, 18), "end": date(2026, 10, 17)}})

    def test_all(self):
        self.assertEqual(window("all", date(2026, 11, 16)), {"start": None, "end": date(2026, 11, 16), "previous": None})

    def test_unknown_period(self):
        with self.assertRaises(ValueError):
            window("week", date(2026, 11, 16))


class JsonTest(unittest.TestCase):
    def test_round_trip(self):
        moment = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)
        session = Session("claude", "cc-12345678", "shop", "/x.jsonl", moment, moment,
                          [Turn(moment, "hi", [Action("Bash", "test")], "completed", 12),
                           Turn(None, "again", [], "unknown", None)], compactions=1, skipped=2)
        self.assertEqual(sessions.session_from_json(sessions.session_to_json(session)), session)

    def test_session_id(self):
        self.assertRegex(sessions.session_id("codex", "/a/b.jsonl"), r"^cx-[0-9a-f]{8}$")


if __name__ == "__main__":
    unittest.main()
