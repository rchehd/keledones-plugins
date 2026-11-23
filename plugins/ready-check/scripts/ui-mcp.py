import base64
import json
import secrets
import sys
from time import monotonic

from ui import TTL, emit, html, start
from ui_state import IDE_STATUSES, VIEWS, View


URI = "ui://ready-check/view.html"
MIME = "text/html;profile=mcp-app"
EXTENSION = "io.modelcontextprotocol/ui"
VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"}


def tool(name, description, properties, required, metadata=None):
    value = dict(name=name, description=description,
                 inputSchema=dict(type="object", properties=properties, required=required, additionalProperties=False))
    if metadata:
        value["_meta"] = dict(ui=metadata)
    return value


def result(data, text=None):
    return dict(content=[dict(type="text", text=text or "Ready Check view response.")], structuredContent=data)


class ReadyUI:
    def __init__(self):
        self.supports_ui = False
        self.views = {}

    def tools(self):
        string = {"type": "string"}
        private = {"resourceUri": URI, "visibility": ["app"]}
        show = tool("show_view", "Open a prepared Ready Check report, project settings, or the Reflect overview.",
                    {"project": string, "task": string, "view": {"type": "string", "enum": list(VIEWS)},
                     "ide_status": {"type": "string", "enum": list(IDE_STATUSES)},
                     "tasks": {"type": "integer", "minimum": 1}, "locale": {"type": "string", "enum": ["en", "uk"]},
                     "snapshot": {"type": "string", "description": "Reflect snapshot ID returned by reflect-collect."}},
                    ["project", "view"], {"resourceUri": URI} if self.supports_ui else None)
        if not self.supports_ui:
            return [show]
        return [show,
                tool("submit_decision", "Record an explicit decision from the Ready Check view.",
                     {"handle": string, "decision": {"type": "object"}}, ["handle", "decision"], private),
                tool("preview_image", "Show an approved image from the current report.",
                     {"handle": string, "path": string}, ["handle", "path"], private),
                tool("local_view", "Open the current view in the local browser.",
                     {"handle": string}, ["handle"], private)]

    def show(self, args):
        view = View(args["project"], args.get("task"), args["view"], args.get("ide_status", "unverified"),
                    args.get("tasks", 10), args.get("locale", "en"), args.get("snapshot"))
        current = view.current()
        state = dict(current, decision=view.decision(current))
        if not self.supports_ui:
            url, _ = start(view)
            return result(dict(url=url, view=view.kind), f"Open Ready Check in a local browser: {url}")
        now = monotonic()
        self.views = {key: session for key, session in self.views.items() if session["expires"] > now}
        if len(self.views) >= 32:
            del self.views[next(iter(self.views))]
        handle = secrets.token_urlsafe(24)
        self.views[handle] = dict(view=view, revision=current["revision"], expires=now + TTL)
        return result(dict(state, handle=handle), "Ready Check opened an interactive view.")

    def call(self, name, args):
        if name == "show_view":
            return self.show(args)
        session = self.views.get(args.get("handle"))
        if not self.supports_ui or not session or session["expires"] <= monotonic():
            raise ValueError("Open the current Ready Check view to continue")
        view = session["view"]
        if name == "submit_decision":
            return result(view.submit(args["decision"]), "Ready Check saved the decision.")
        if name == "local_view":
            view.current(session["revision"])
            if "url" not in session:
                session["url"], _ = start(view, revision=session["revision"])
            return result({"url": session["url"]})
        if name == "preview_image":
            path, mime = view.artifact(args["path"], session["revision"])
            if not mime.startswith("image/"):
                raise ValueError("Expected an image from the current report")
            if path.stat().st_size > 4_000_000:
                return result({"open_local": True}, "Open the local report to view this evidence.")
            return result(dict(mimeType=mime, data=base64.b64encode(path.read_bytes()).decode("ascii")))
        raise ValueError("Unknown Ready Check UI tool")

    def handle(self, method, params):
        if method == "initialize":
            extension = params.get("capabilities", {}).get("extensions", {}).get(EXTENSION, {})
            self.supports_ui = MIME in extension.get("mimeTypes", [])
            version = params["protocolVersion"]
            return dict(protocolVersion=version if version in VERSIONS else "2025-11-25",
                        serverInfo=dict(name="ready-ui", version="1.0.0"), capabilities=dict(tools={}, resources={}))
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools()}
        if method == "tools/call":
            try:
                return self.call(params["name"], params.get("arguments", {}))
            except (OSError, ValueError, TypeError, KeyError) as error:
                return dict(isError=True, content=[dict(type="text", text=str(error))])
        if method == "resources/list":
            return dict(resources=[dict(uri=URI, name="Ready Check", mimeType=MIME)] if self.supports_ui else [])
        if method == "resources/read" and self.supports_ui and params.get("uri") == URI:
            return dict(contents=[dict(uri=URI, mimeType=MIME, text=html())])
        raise ValueError("Unsupported MCP request")


def main():
    server = ReadyUI()
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise ValueError("Expected a JSON-RPC request")
            if "id" not in request:
                continue
            response = server.handle(request["method"], request.get("params", {}))
            emit(dict(jsonrpc="2.0", id=request["id"], result=response))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            emit(dict(jsonrpc="2.0", id=request.get("id") if isinstance(request, dict) else None,
                      error=dict(code=-32602, message=str(error))))
    return 0
