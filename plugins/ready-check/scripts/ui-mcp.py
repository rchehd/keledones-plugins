import base64
import json
import secrets
import sys
from pathlib import Path
from time import monotonic
from urllib.parse import unquote

from ui import TTL, emit, html, start
from ui_state import ASSET_TYPES, View


URI = "ui://ready-check/view.html"
VIDEO_RESOURCE_PREFIX = "ready-check-video://evidence/"
MIME = "text/html;profile=mcp-app"
EXTENSION = "io.modelcontextprotocol/ui"
INLINE_MEDIA_LIMIT = 4_000_000
PREVIEW_IMAGE_LIMIT = 128_000
PREVIEW_TOTAL_LIMIT = 384_000
VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"}


def tool(name, description, properties, required, metadata=None):
    value = dict(name=name, description=description,
                 inputSchema=dict(type="object", properties=properties, required=required, additionalProperties=False))
    if metadata:
        value["_meta"] = dict(ui=metadata)
    return value


def result(data, text=None):
    return dict(content=[dict(type="text", text=text or "Ready Check view response.")], structuredContent=data)


def read_bounded(path, limit):
    with path.open("rb") as source:
        data = source.read(limit + 1)
    return data if 0 < len(data) <= limit else None


def inline_media(mime, data):
    return dict(mimeType=mime, data=base64.b64encode(data).decode("ascii"))


def media_preview(session, name, mime_prefix):
    path, mime = session["view"].artifact(name, session["revision"])
    if mime.startswith(mime_prefix):
        data = read_bounded(path, INLINE_MEDIA_LIMIT)
        if data is not None:
            return inline_media(mime, data)
    return None


def screenshot_previews(view, current):
    previews = {}
    remaining = PREVIEW_TOTAL_LIMIT
    for case in current["data"]["scenarios"]:
        for asset in case.get("artifacts", []):
            name = asset["path"]
            mime = ASSET_TYPES.get(Path(name).suffix.lower(), "")
            if name in previews or not mime.startswith("image/"):
                continue
            try:
                path = view.artifact_path(name)
                data = read_bounded(path, min(PREVIEW_IMAGE_LIMIT, remaining))
            except (OSError, ValueError):
                continue
            if data is None:
                continue
            previews[name] = inline_media(mime, data)
            remaining -= len(data)
            if not remaining:
                return previews
    return previews


class ReadyUI:
    def __init__(self):
        self.supports_ui = False
        self.views = {}

    def tools(self):
        string = {"type": "string"}
        private = {"resourceUri": URI, "visibility": ["app"]}
        show = tool("show_view", "Show the prepared QA round. Prepare its display text in the chat language before opening it.",
                    {"project": string, "task": string, "view": {"type": "string", "enum": ["qa-results"]}},
                    ["project", "task", "view"], {"resourceUri": URI} if self.supports_ui else None)
        if not self.supports_ui:
            return [show]
        return [show,
                tool("preview_media", "Show a listed screenshot or recording from the current QA round.",
                     {"handle": string, "path": string}, ["handle", "path"], private),
                tool("local_view", "Open the current view in the local browser.",
                     {"handle": string}, ["handle"], private)]

    def show(self, args):
        if args["view"] != "qa-results":
            raise ValueError("The Ready Check MCP App only displays QA results")
        view = View(args["project"], args["task"], "qa-results")
        current = view.current(require_current_round=True)
        now = monotonic()
        self.views = {key: session for key, session in self.views.items() if session["expires"] > now}
        if len(self.views) >= 32:
            evicted = self.views.pop(next(iter(self.views)))
            if "close" in evicted:
                evicted["close"]()
        handle = secrets.token_urlsafe(24)
        session = dict(view=view, revision=current["revision"], expires=now + TTL)
        try:
            url = self.local_url(session)
        except OSError:
            if not self.supports_ui:
                raise
            url = None
        self.views[handle] = session
        if not self.supports_ui:
            return result(dict(url=url, view=view.kind), f"Open this local Ready Check report in the client's browser: {url}")
        response = result(dict(current, handle=handle, url=url), "Ready Check opened the QA evidence.")
        previews = screenshot_previews(view, current)
        if previews:
            response["_meta"] = {"readyCheckPreviews": previews}
        return response

    def local_url(self, session):
        if "url" not in session:
            session["url"], _, session["close"] = start(session["view"], revision=session["revision"])
        return session["url"]

    def view_session(self, handle):
        session = self.views.get(handle)
        if not self.supports_ui or not session or session["expires"] <= monotonic():
            raise ValueError("Open the current Ready Check view to continue")
        return session

    def resource(self, uri):
        if uri == URI:
            return dict(contents=[dict(uri=URI, mimeType=MIME, text=html())])
        if not isinstance(uri, str) or not uri.startswith(VIDEO_RESOURCE_PREFIX):
            raise ValueError("Unsupported MCP resource")
        handle, separator, name = uri[len(VIDEO_RESOURCE_PREFIX):].partition("/")
        if not separator or not name:
            raise ValueError("A Ready Check recording URI is required")
        preview = media_preview(self.view_session(handle), unquote(name, errors="strict"), "video/")
        if preview is None:
            raise ValueError("Open the local report to view this evidence.")
        return dict(contents=[dict(uri=uri, mimeType=preview["mimeType"], blob=preview["data"])])

    def call(self, name, args):
        if name == "show_view":
            return self.show(args)
        session = self.view_session(args.get("handle"))
        if name == "local_view":
            session["view"].current(session["revision"], require_current_round=True)
            return result({"url": self.local_url(session)})
        if name == "preview_media":
            preview = media_preview(session, args["path"], ("image/", "video/"))
            if preview is None:
                return result({"open_local": True}, "Open the local report to view this evidence.")
            return result(preview)
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
        if method == "resources/templates/list":
            template = dict(uriTemplate=VIDEO_RESOURCE_PREFIX + "{handle}/{path}", name="Ready Check recording")
            return dict(resourceTemplates=[template] if self.supports_ui else [])
        if method == "resources/read" and self.supports_ui:
            return self.resource(params.get("uri"))
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
