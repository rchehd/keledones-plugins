import json
import unittest

from helpers import RepoTest
import answers

QUESTION = {"question": "Which checks should run?", "header": "Checks",
            "options": [{"label": "All checks"}, {"label": "Static only"}], "multiSelect": False}


class AnswerTextTest(unittest.TestCase):
    def test_claude_answers_map(self):
        payload = {"tool_name": "AskUserQuestion", "tool_input": {"questions": [QUESTION]},
                   "tool_response": {"questions": [QUESTION], "answers": {"Which checks should run?": "All checks"}}}
        self.assertEqual(answers.text(payload), "Q: Which checks should run?\nA: All checks")

    def test_claude_answers_as_text(self):
        payload = {"tool_name": "AskUserQuestion", "tool_input": {"questions": [QUESTION]},
                   "tool_response": 'Your questions have been answered: "Which checks should run?"="Static only".'}
        self.assertEqual(answers.text(payload), "Q: Which checks should run?\nA: Static only")

    def test_codex_answers_by_question_id(self):
        payload = {"tool_name": "request_user_input",
                   "tool_input": {"questions": [{"id": "checks", "question": "Which checks should run?",
                                                 "options": [{"label": "All checks"}]}]},
                   "tool_response": json.dumps({"answers": {"checks": {"answers": ["All checks"]}}})}
        self.assertEqual(answers.text(payload), "Q: Which checks should run?\nA: All checks")

    def test_cursor_selected_option_ids(self):
        payload = {"tool_name": "AskQuestion",
                   "tool_input": {"questions": [{"id": "q1", "prompt": "Which browser mode?",
                                                 "options": [{"id": "v", "label": "Visible"}, {"id": "b", "label": "Background"}]}]},
                   "tool_output": json.dumps({"outcome": {"outcome": "answered",
                                                          "answers": [{"questionId": "q1", "selectedOptionIds": ["b"]}]}})}
        self.assertEqual(answers.text(payload), "Q: Which browser mode?\nA: Background")

    def test_other_tools_and_empty_answers_are_ignored(self):
        self.assertIsNone(answers.text({"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": "x"}))
        self.assertIsNone(answers.text({"tool_name": "AskUserQuestion", "tool_input": {"questions": [QUESTION]},
                                        "tool_response": {"answers": {}}}))


class AnswerHookTest(RepoTest):
    def hook(self, event, client, payload):
        process = self.run_entry("hook", event, "--client", client, stdin=json.dumps(payload))
        self.assertEqual(process.returncode, 0, process.stderr)
        return process.stdout.strip()

    def records(self):
        return [json.loads(line)["prompt"] for path in (self.repo / ".ai/ready-check/tasks").glob("*/*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]

    def test_answer_is_recorded_once_even_when_it_also_arrives_as_a_prompt(self):
        reply = '<send_user_message_question_reply>[{"question": "Which checks should run?", "answer": "All checks"}]</send_user_message_question_reply>'
        self.hook("prompt", "codex", {"cwd": str(self.repo), "session_id": "s", "prompt": reply})
        self.assertEqual(self.hook("answer", "codex", {
            "cwd": str(self.repo), "session_id": "s", "tool_name": "request_user_input",
            "tool_input": {"questions": [{"id": "c", "question": "Which checks should run?"}]},
            "tool_response": {"answers": {"c": {"answers": ["All checks"]}}}}), "")
        self.assertEqual(self.records(), ["Q: Which checks should run?\nA: All checks"])

    def test_capture_setting_turns_answer_records_off(self):
        self.entry_json("config", "set", "captureTasks", "false", "--project", str(self.repo))
        self.hook("answer", "claude", {"cwd": str(self.repo), "session_id": "s", "tool_name": "AskUserQuestion",
                                       "tool_input": {"questions": [QUESTION]},
                                       "tool_response": {"answers": {"Which checks should run?": "All checks"}}})
        self.assertFalse((self.repo / ".ai/ready-check/tasks").exists())


if __name__ == "__main__":
    unittest.main()
