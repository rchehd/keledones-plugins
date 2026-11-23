import argparse
import json
import re
import secrets
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread, Timer
from urllib.parse import parse_qs, urlsplit

from project import toplevel
from ui_state import IDE_STATUSES, VIEWS, View, reviewed_source


ASSETS = Path(__file__).resolve().parent.parent / "ui"
TTL = 900
MAX_DECISION = 64_000
RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def html():
    return (ASSETS / "dist/index.html").read_text(encoding="utf-8")


class LocalView(ThreadingHTTPServer):
    def __init__(self, view, revision=None):
        super().__init__(("127.0.0.1", 0), Handler)
        self.view = view
        self.revision = revision
        self.host = f"127.0.0.1:{self.server_port}"
        self.origin = f"http://{self.host}"
        self.token = secrets.token_urlsafe(32)
        self.url = f"{self.origin}/#{self.token}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def allowed_host(self):
        return self.headers.get("Host") == self.server.host

    def authorized(self):
        header = self.headers.get("Authorization", "").removeprefix("Bearer ")
        return header.isascii() and secrets.compare_digest(header, self.server.token)

    def respond(self, status, content_type, size):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def send_bytes(self, data, content_type, status=200, html_page=False):
        self.respond(status, content_type, len(data))
        if html_page:
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; media-src 'self'; "
                             "form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, data, status=200):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode(), "application/json", status)

    def do_GET(self):
        if not self.allowed_host():
            self.send_json({"error": "Unexpected request host"}, 403)
            return
        url = urlsplit(self.path)
        try:
            if url.path == "/":
                self.send_bytes(html().encode(), "text/html; charset=utf-8", html_page=True)
            elif url.path == "/state" and self.authorized():
                current = self.server.view.current(self.server.revision)
                self.send_json(dict(current, decision=self.server.view.decision(current)))
            elif url.path == "/asset":
                query = parse_qs(url.query)
                token = query.get("access", [""])[0]
                if not token.isascii() or not secrets.compare_digest(token, self.server.token):
                    self.send_json({"error": "Evidence access expired"}, 403)
                    return
                revision = query.get("revision", [""])[0]
                if self.server.revision is not None and revision != self.server.revision:
                    raise ValueError("This view is out of date. Open the current round or revision.")
                path, media_type = self.server.view.artifact(query.get("name", [""])[0], revision)
                self.send_asset(path, media_type)
            else:
                self.send_json({"error": "Resource unavailable"}, 404)
        except (OSError, ValueError, TypeError, KeyError) as error:
            if not isinstance(error, (BrokenPipeError, ConnectionResetError)):
                self.send_json({"error": str(error)}, 400)

    def do_POST(self):
        if (self.path != "/decision" or not self.allowed_host() or not self.authorized()
                or self.headers.get("Origin", self.server.origin) != self.server.origin):
            self.send_json({"error": "Decision access denied"}, 403)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= MAX_DECISION or self.headers.get_content_type() != "application/json":
                raise ValueError("Expected a bounded JSON decision")
            request = json.loads(self.rfile.read(size))
            self.send_json(self.server.view.submit(request))
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.send_json({"error": str(error)}, 400)

    def send_asset(self, path, media_type):
        with path.open("rb") as source:
            size = path.stat().st_size
            header = self.headers.get("Range")
            if not header:
                self.respond(200, media_type, size)
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                shutil.copyfileobj(source, self.wfile, length=64_000)
                return
            match = RANGE.fullmatch(header)
            if not match or not any(match.groups()):
                self.unsupported_range(size)
                return
            left, right = match.groups()
            start = int(left) if left else max(0, size - int(right))
            end = min(int(right), size - 1) if left and right else size - 1
            if not 0 <= start <= end < size:
                self.unsupported_range(size)
                return
            remaining = end - start + 1
            self.respond(206, media_type, remaining)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            source.seek(start)
            while remaining:
                block = source.read(min(remaining, 64_000))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)

    def unsupported_range(self, size):
        self.respond(416, "text/plain", 0)
        self.send_header("Content-Range", f"bytes */{size}")
        self.end_headers()


def start(view, ttl=TTL, revision=None):
    server = LocalView(view, revision)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def close():
        server.shutdown()
        server.server_close()

    timer = Timer(ttl, close)
    timer.daemon = True
    timer.start()
    return server.url, thread


def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Prepare, open, or read a Ready Check interactive view.")
    parser.add_argument("operation", choices=("snapshot", "prepare", "serve", "decision"))
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--task")
    parser.add_argument("--view", required=True, choices=VIEWS)
    parser.add_argument("--input", help="JSON file relative to the task report")
    parser.add_argument("--ttl", type=int, default=TTL)
    parser.add_argument("--ide-status", choices=IDE_STATUSES, default="unverified")
    args = parser.parse_args()
    try:
        if args.operation == "snapshot":
            root = toplevel(args.project)
            if args.view != "review" or not root:
                raise ValueError("A Git project and the review view are required for a source snapshot")
            emit(dict(status="PASS", reviewed_source=reviewed_source(root)))
            return 0
        view = View(args.project, args.task, args.view, args.ide_status)
        if args.operation == "prepare":
            if not args.input:
                raise ValueError("View preparation requires --input")
            emit({"status": "PASS", **view.prepare(args.input)})
        elif args.operation == "decision":
            current = view.current()
            decision = view.decision(current)
            result = dict(status="PASS" if decision else "PENDING", decision=decision)
            if view.kind == "qa-results":
                previous = view.previous_gallery_decisions(current)
                result["previous_decisions"] = previous
                if previous:
                    result["status"] = "PASS"
            emit(result)
        else:
            if not 1 <= args.ttl <= TTL:
                raise ValueError(f"--ttl must be between 1 and {TTL} seconds")
            view.current()
            url, thread = start(view, args.ttl)
            emit(dict(status="PASS", url=url, expires_in=args.ttl))
            thread.join()
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        emit(dict(status="INCOMPLETE", reason=str(error)))
        return 2
