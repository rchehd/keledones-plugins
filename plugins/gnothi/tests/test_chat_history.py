import json
import unittest
from datetime import date, datetime, timezone
from zipfile import ZipFile

from helpers import TempHome
from test_loading import install_fixtures
import digest
import gnothi
import report
from sources import chat_history

TODAY = date(2026, 11, 16)


def node(parent, role, text, month=11, **metadata):
    return {"parent": parent, "message": {
        "author": {"role": role},
        "create_time": datetime(2026, month, 11, 12, tzinfo=timezone.utc).timestamp(),
        "content": {"content_type": "text", "parts": [text, {"asset_pointer": "private-attachment"}]},
        "metadata": metadata,
    }}


class ChatHistoryTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)
        self.chatgpt = {"id": "private-chatgpt-id", "title": "private-title", "current_node": "answer", "mapping": {
            "root": {"parent": None, "message": None},
            "first": node("root", "user", "Plan my trip", month=10),
            "unused": node("first", "user", "discarded-branch"),
            "hidden": node("first", "user", "hidden-user-message", is_visually_hidden_from_conversation=True),
            "follow-up": node("hidden", "user", "Send the details to person@example.com"),
            "answer": node("follow-up", "assistant", "assistant-message"),
        }}
        self.claude = {"uuid": "private-claude-id", "chat_messages": [
            {"sender": "human", "created_at": "2026-11-12T13:00:00.000Z",
             "content": [{"type": "text", "text": "Explain the difference"}]},
            {"sender": "assistant", "created_at": "2026-11-12T13:05:00Z", "text": "assistant-message"},
        ]}

    def write(self, name, data):
        path = self.home.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_combine_agent_logs_and_both_chat_exports(self):
        install_fixtures(self.home)
        archive = self.home.root / "chatgpt.zip"
        with ZipFile(archive, "w") as exported:
            exported.writestr("export/conversations-001.json", json.dumps([self.chatgpt]))
            exported.writestr("export/conversations-002.json", json.dumps([self.chatgpt]))
            exported.writestr("account.json", "must never be opened")
        claude = self.write("claude.json", [self.claude])

        baseline = digest.build("month", TODAY)
        data = digest.build("month", TODAY, chat_exports=[archive, claude])
        self.assertEqual({source["client"]: source["sessions"] for source in data["sources"]},
                         dict(claude=1, codex=1, cursor=1, chatgpt=1, **{"claude-chat": 1}))
        self.assertEqual(data["previous"]["summary"]["sessions"], 1)
        self.assertEqual(data["current"]["summary"]["agent_sessions"], 3)
        for axis in ("focus", "completion", "tool_range"):
            self.assertEqual(data["current"]["axes"][axis], baseline["current"]["axes"][axis])
        chatgpt = next(entry for entry in data["evidence"] if entry["client"] == "chatgpt")
        self.assertEqual(chatgpt["turns"], 1)
        self.assertIn("Send the details to ", chatgpt["excerpts"][0])
        serialized = json.dumps(data)
        for private_text in ("person@example.com", "private-chatgpt-id", "private-claude-id", "private-title",
                             "discarded-branch", "hidden-user-message", "assistant-message", "private-attachment"):
            self.assertNotIn(private_text, serialized)

    def test_native_sample_uses_same_conversation_identity_and_records_coverage(self):
        sample = self.write("sample.json", {"source": "chatgpt", "conversations": [
            {"id": self.chatgpt["id"], "messages": [
                {"role": "user", "timestamp": "2026-11-11T12:00:00Z", "text": "Same conversation"}
            ]},
        ]})
        export = self.write("conversations.json", [self.chatgpt])
        args = gnothi.parser().parse_args(["sources", "--chat-export", str(export), "--chat-sample", str(sample)])
        entry = gnothi.sources(args)["sources"][-1]
        self.assertEqual((entry["imports"], entry["files"], entry["sessions"]), (["export", "sample"], 2, 1))

    def test_chat_only_renders_and_leaves_agent_metrics_unavailable(self):
        export = self.write("conversations.json", [self.chatgpt])
        data = digest.build("all", TODAY, metrics_only=True, archetypes_on=True, chat_exports=[export])
        self.assertEqual(data["current"]["summary"]["sessions"], 1)
        self.assertEqual(data["current"]["summary"]["agent_sessions"], 0)
        self.assertIsNone(data["current"]["axes"]["completion"])
        self.assertIsNone(data["current"]["archetypes"])
        self.assertEqual([point["month"] for point in data["trend"]], ["2026-10", "2026-11"])
        self.assertEqual(data["evidence"], [])
        self.assertNotIn("Send the details", json.dumps(data))
        html = report.render_html(data, {"summary": "Sample"}, {"epochs": []}, None)
        self.assertIn("ChatGPT", html)
        self.assertIn("Chat history source", html)

    def test_regenerated_branches_without_a_selected_leaf_are_skipped(self):
        del self.chatgpt["current_node"]
        sessions, sources = chat_history.import_sources([self.write("conversations.json", [self.chatgpt])])
        self.assertEqual(sessions, [])
        self.assertEqual(sources[0]["skipped_conversations"], 1)

    def test_zip_without_conversations_reports_error(self):
        path = self.home.root / "account.zip"
        with ZipFile(path, "w") as exported:
            exported.writestr("account.json", "{}")
        with self.assertRaisesRegex(ValueError, "no conversations JSON"):
            chat_history.import_sources([path])
