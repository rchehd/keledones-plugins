import json
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import PLUGIN, TempHome

import widget


class WidgetTest(unittest.TestCase):
    def test_opted_in_metrics_work_in_mcp_and_the_offline_bundle(self):
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
            identifier = prepared["widget_id"]
            offline = Path(prepared["widget_html"]).read_text(encoding="utf-8")
            self.assertIn("Робочий портрет Gnothi", offline)
            self.assertIn('"previous": 6.5', offline)
            self.assertNotIn("Private session fixture", offline)
            calls = [
                ("initialize", {"protocolVersion": "2025-11-25"}),
                ("tools/call", {"name": "show_portrait", "arguments": {"widget_id": identifier}}),
                ("initialize", {"protocolVersion": "2025-11-25", "capabilities": {
                    "extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}}),
                ("tools/list", {}),
                ("tools/call", {"name": "show_portrait", "arguments": {"widget_id": identifier}}),
                ("tools/call", {"name": "show_portrait", "arguments": {"widget_id": "../digest.json"}}),
            ]
            requests = "".join(json.dumps(dict(jsonrpc="2.0", id=i, method=method, params=params)) + "\n"
                               for i, (method, params) in enumerate(calls))
            response = subprocess.check_output([sys.executable, str(PLUGIN / "scripts/widget-mcp.py")],
                                               input=requests, encoding="utf-8")
            replies = [json.loads(line)["result"] for line in response.splitlines()]
            self.assertEqual(replies[1]["structuredContent"]["html"], prepared["widget_html"])
            self.assertEqual(replies[3]["tools"][0]["_meta"]["ui"]["resourceUri"], "ui://gnothi/portrait.html")
            self.assertEqual(replies[4]["structuredContent"]["metrics"][0], {"label": "Сесії", "value": 5, "previous": 2})
            self.assertNotIn("Confidential project fixture", response)
            self.assertNotIn("Private session fixture", response)
            self.assertTrue(replies[5]["isError"])
