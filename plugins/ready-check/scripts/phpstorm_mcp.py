import http.client
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import git_exclude
from project import redirected, write_json


CURSOR_CONFIG = Path(".cursor/mcp.json")
SERVER_NAME = "ready-check-phpstorm"
PROJECT_HEADER = "IJ_MCP_SERVER_PROJECT_PATH"
INSPECTIONS = {"lint_files", "get_file_problems"}
MAX_RESPONSE = 1024 * 1024


def stream_url(url):
    try:
        address = urlsplit(url)
        if (address.scheme == "http" and address.hostname in {"localhost", "127.0.0.1"} and address.port
                and address.username is None and address.path == "/stream" and not (address.query or address.fragment)):
            return f"http://127.0.0.1:{address.port}/stream"
    except ValueError:
        pass
    return None


def load_cursor_config(top):
    path = top / CURSOR_CONFIG
    if redirected(path.parent) or redirected(path) or path.exists() and not path.is_file():
        raise ValueError("Cursor MCP config must be a regular file inside the project")
    try:
        original = path.read_bytes() if path.exists() else None
        data = json.loads(original.decode("utf-8-sig")) if original is not None else {}
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError("Cursor MCP config must contain valid JSON before Ready Check can update it") from error
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("Cursor MCP config must contain an mcpServers object")
    return data, original


def existing_endpoint(name, entry):
    if "phpstorm" in name.lower() and isinstance(entry, dict) and isinstance(entry.get("url"), str):
        headers = entry.get("headers", {})
        if isinstance(headers, dict) and headers.get(PROJECT_HEADER, "${workspaceFolder}") == "${workspaceFolder}":
            return stream_url(entry["url"])
    return None


def listening_ports():
    if sys.platform != "linux":
        return []
    try:
        sockets = subprocess.run(["ss", "-H", "-ltnp"], capture_output=True, text=True, timeout=2, check=True)
    except (OSError, subprocess.SubprocessError):
        return []
    ports = []
    for line in sockets.stdout.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or '("phpstorm",' not in fields[5]:
            continue
        host, _, port = fields[3].rpartition(":")
        if host in {"127.0.0.1", "[::ffff:127.0.0.1]"} and port.isascii() and port.isdecimal():
            ports.append(int(port))
    return ports


def rpc(port, headers, method, params, request_id=None):
    message = dict(jsonrpc="2.0", method=method, params=params)
    if request_id is not None:
        message["id"] = request_id
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("POST", "/stream", json.dumps(message), headers)
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise ValueError("PhpStorm MCP request failed")
        if session := response.getheader("Mcp-Session-Id"):
            headers["Mcp-Session-Id"] = session
        if request_id is None:
            return {}
        if response.getheader("Content-Type", "").startswith("text/event-stream"):
            remaining = MAX_RESPONSE
            while remaining and (line := response.readline(remaining)):
                remaining -= len(line)
                if line.startswith(b"data:"):
                    payload = json.loads(line[5:])
                    if isinstance(payload, dict) and payload.get("id") == request_id:
                        return payload["result"]
            raise ValueError("PhpStorm MCP did not return a response")
        body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise ValueError("PhpStorm MCP response exceeds the probe limit")
        payload = json.loads(body)
        if payload.get("id") != request_id:
            raise ValueError("PhpStorm MCP returned an unexpected response")
        return payload["result"]
    finally:
        connection.close()


def project_probe(top, tools):
    if "get_project_modules" in tools:
        return "get_project_modules", dict(projectPath=str(top))

    tracked = git_exclude.git(top, "ls-files", "-z", "--cached") or ""
    extensions = {".php", ".module", ".inc", ".theme", ".py", ".js", ".ts", ".json", ".md"}
    for name in tracked.split("\0"):
        file = top / name
        if file.suffix.lower() not in extensions or not file.is_file() or redirected(file):
            continue
        if "get_file_problems" in tools:
            return "get_file_problems", dict(projectPath=str(top), filePath=name, errorsOnly=False)
        return "lint_files", dict(projectPath=str(top), files=[name], min_severity="warning")
    return None


def verified_endpoint(top, url):
    port = urlsplit(url).port
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    try:
        result = rpc(port, headers, "initialize", dict(protocolVersion="2025-03-26", capabilities={},
                     clientInfo=dict(name="Ready Check", version="1.0.0")), 1)
        if "phpstorm" not in result["serverInfo"]["name"].lower():
            return False
        headers["MCP-Protocol-Version"] = result["protocolVersion"]
        rpc(port, headers, "notifications/initialized", {})
        tools = {tool["name"] for tool in rpc(port, headers, "tools/list", {}, 2)["tools"]}
        if not tools & INSPECTIONS or not (probe := project_probe(top, tools)):
            return False
        name, arguments = probe
        project = rpc(port, headers, "tools/call", dict(name=name, arguments=arguments), 3)
        return not project.get("isError")
    except (OSError, ValueError, AttributeError, KeyError, TypeError, http.client.HTTPException):
        return False


def discover_cursor(top, explicit_url=None):
    if explicit_url is not None:
        url = stream_url(explicit_url)
        if not url:
            raise ValueError("Use the local PhpStorm MCP HTTP /stream URL from the IDE settings")
        return url if verified_endpoint(top, url) else None
    data, _ = load_cursor_config(top)
    servers = data.get("mcpServers", {})
    configured = [url for name, entry in servers.items() if (url := existing_endpoint(name, entry))]
    ports = sorted(listening_ports(), key=lambda port: (not 64342 <= port < 65000, port))
    candidates = configured + [f"http://127.0.0.1:{port}/stream" for port in (64342, *ports)]
    return next((url for url in dict.fromkeys(candidates) if verified_endpoint(top, url)), None)


def cursor_entry(url, *, project_header=True):
    entry = dict(url=url)
    if project_header:
        entry["headers"] = {PROJECT_HEADER: "${workspaceFolder}"}
    return entry


def register_cursor(top, url):
    data, original = load_cursor_config(top)
    servers = data.setdefault("mcpServers", {})
    project_header = str(top).isascii()
    for name, entry in servers.items():
        if existing_endpoint(name, entry) == url:
            if project_header or PROJECT_HEADER not in entry.get("headers", {}):
                return dict(status="ALREADY_REGISTERED", server=name, restart_required=False)

    if SERVER_NAME in servers:
        previous = existing_endpoint(SERVER_NAME, servers[SERVER_NAME])
        if not previous or servers[SERVER_NAME] not in (cursor_entry(previous), cursor_entry(previous, project_header=False)):
            raise ValueError(f"Cursor already has a custom {SERVER_NAME} MCP entry")

    relative = CURSOR_CONFIG.as_posix()
    tracked = git_exclude.git(top, "ls-files", "--", relative)
    if tracked is None or tracked:
        raise ValueError("Cannot write a local PhpStorm connection into a tracked Cursor MCP config")
    if not git_exclude.git(top, "check-ignore", "--", relative):
        exclude = git_exclude.plan(top, [relative])
        if exclude is None:
            raise ValueError("Could not find the local Git exclude file for Cursor MCP config")
        git_exclude.apply(exclude, merge_entries=True)
        if not git_exclude.git(top, "check-ignore", "--", relative):
            raise ValueError("Git does not ignore the local Cursor MCP config")

    servers[SERVER_NAME] = cursor_entry(url, project_header=project_header)
    write_json(top / CURSOR_CONFIG, data, top, original=original)
    return dict(status="REGISTERED", server=SERVER_NAME, restart_required=True)
