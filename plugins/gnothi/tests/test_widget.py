import json
import unittest
from pathlib import Path

from helpers import PLUGIN, TempHome

import widget


class WidgetTest(unittest.TestCase):
    def test_aggregate_metrics_are_written_to_private_html(self):
        with TempHome():
            digest = {
                "period": {"start": "2026-11-01", "end": "2026-11-23",
                           "previous": {"start": "2026-10-01", "end": "2026-10-23"}},
                "current": {"summary": {"sessions": 5, "requests": 12, "active_days": 3},
                            "axes": {"clarity": 8.5}},
                "previous": {"summary": {"sessions": 2}, "axes": {"clarity": 6.5}},
                "evidence": [{"excerpts": ["Private session fixture"]}],
                "projects": [{"name": "Confidential project fixture"}],
            }
            prepared = widget.prepare(digest, "uk")
            offline = Path(prepared["widget_html"]).read_text(encoding="utf-8")
            self.assertIn("Робочий портрет Gnothi", offline)
            self.assertIn('"previous": 6.5', offline)
            self.assertNotIn("Private session fixture", offline)
            self.assertIn('"label": "Сесії", "value": 5, "previous": 2', offline)
            self.assertNotIn("Confidential project fixture", offline)
            self.assertNotIn("ui/initialize", offline)

    def test_no_plugin_manifest_registers_the_retired_mcp_view(self):
        self.assertFalse((PLUGIN / ".mcp.json").exists())
        for name in (".claude-plugin", ".codex-plugin", ".cursor-plugin"):
            manifest = json.loads((PLUGIN / name / "plugin.json").read_text(encoding="utf-8"))
            self.assertNotIn("gnothi-ui", manifest.get("mcpServers", {}))
