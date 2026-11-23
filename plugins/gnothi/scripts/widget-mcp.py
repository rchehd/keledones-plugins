from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True
from widget import ASSET, load


URI = "ui://gnothi/portrait.html"
MIME = "text/html;profile=mcp-app"
VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"}


def response(data, message, error=False):
    return dict(content=[dict(type="text", text=message)], structuredContent=data, isError=error)


class GnothiWidget:
    def __init__(self):
        self.supports_ui = False

    def handle(self, method, params):
        if method == "initialize":
            extensions = params.get("capabilities", {}).get("extensions", {})
            self.supports_ui = MIME in extensions.get("io.modelcontextprotocol/ui", {}).get("mimeTypes", [])
            version = params["protocolVersion"]
            return dict(protocolVersion=version if version in VERSIONS else "2025-11-25",
                        serverInfo=dict(name="gnothi-ui", version="1.0.0"), capabilities=dict(tools={}, resources={}))
        if method == "ping":
            return {}
        if method == "tools/list":
            tool = dict(name="show_portrait", description="Open an approved Gnothi aggregate metrics view.",
                        inputSchema=dict(type="object", properties={"widget_id": {"type": "string"}},
                                         required=["widget_id"], additionalProperties=False))
            if self.supports_ui:
                tool["_meta"] = {"ui": {"resourceUri": URI}}
            return {"tools": [tool]}
        if method == "tools/call" and params.get("name") == "show_portrait":
            try:
                data, path = load(params.get("arguments", {}).get("widget_id"))
            except (OSError, ValueError) as error:
                return response({}, str(error), error=True)
            return response(data, "Gnothi opened an approved metrics view.") if self.supports_ui else response(
                {"html": path}, "Open the private Gnothi HTML report: " + path)
        if method == "resources/list":
            return {"resources": [dict(uri=URI, name="Gnothi portrait", mimeType=MIME)] if self.supports_ui else []}
        if method == "resources/read" and self.supports_ui and params.get("uri") == URI:
            return {"contents": [dict(uri=URI, mimeType=MIME, text=ASSET.read_text(encoding="utf-8"))]}
        raise ValueError("Unsupported Gnothi MCP request")


def main():
    server = GnothiWidget()
    for line in sys.stdin:
        request_id = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise ValueError("Expected a JSON-RPC request")
            if "id" not in request:
                continue
            request_id = request["id"]
            result = server.handle(request["method"], request.get("params", {}))
            result = {"result": result}
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            result = {"error": {"code": -32602, "message": str(error)}}
        print(json.dumps(dict(jsonrpc="2.0", id=request_id, **result)), flush=True)


if __name__ == "__main__":
    main()
