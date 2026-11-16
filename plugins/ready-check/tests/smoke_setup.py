import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
from process_support import stop_tree


def mcp_smoke(project, env, command, reports=None, headed=False, argv=None, name=None):
    class Fixture(BaseHTTPRequestHandler):
        def do_GET(self):
            content = b'<button onclick="document.title=String(42)">Smoke</button>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass
    name = name or ("mcp-headed" if headed else "mcp-headless")
    argv = argv or [*command, "mcp", "--project", str(project), "--headed" if headed else "--headless"]
    log = reports / (name + ".log") if reports else project.parent / (name + ".log")
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with log.open("w", encoding="utf-8") as stderr, HTTPServer(("127.0.0.1", 0), Fixture) as site:
        web = threading.Thread(target=site.serve_forever, daemon=True)
        web.start()
        process = subprocess.Popen(argv, cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            text=True, encoding="utf-8", **options)
        responses = queue.Queue()
        def read():
            for line in process.stdout:
                responses.put(line)
            responses.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        count = 0
        def send(value):
            process.stdin.write(json.dumps(value) + "\n")
            process.stdin.flush()
        def request(method, params):
            nonlocal count
            count += 1
            send(dict(jsonrpc="2.0", id=count, method=method, params=params))
            while True:
                line = responses.get(timeout=90)
                if line is None:
                    raise RuntimeError("MCP closed its output; inspect " + str(log))
                response = json.loads(line)
                if response.get("id") != count:
                    continue
                if response.get("error") or response.get("result", {}).get("isError"):
                    raise RuntimeError("MCP request failed: " + json.dumps(response))
                return response["result"]
        try:
            identity = request("initialize", dict(protocolVersion="2024-11-05", capabilities={}, clientInfo=dict(name="ready-check-smoke", version="1")))
            send(dict(jsonrpc="2.0", method="notifications/initialized"))
            definitions = request("tools/list", {})["tools"]
            schemas = {tool["name"]: tool["inputSchema"].get("properties", {}) for tool in definitions}
            tools = set(schemas)
            if reports:
                (reports / "mcp-tools.json").write_text(json.dumps(definitions, indent=2), encoding="utf-8")
            if not {"browser_navigate", "browser_click", "browser_evaluate", "browser_close"} <= tools:
                raise RuntimeError("Official MCP browser tools are unavailable: " + ", ".join(sorted(tools)))
            page = request("tools/call", dict(name="browser_navigate", arguments=dict(url=f"http://127.0.0.1:{site.server_port}")))
            snapshot = "\n".join(part.get("text", "") for part in page.get("content", []))
            artifact = re.search(r'\[Snapshot\]\(([^)]+)\)', snapshot)
            if artifact:
                path = (project / artifact[1]).resolve()
                if not path.is_relative_to(project / "ai/ready-check/tmp/playwright-mcp"):
                    raise RuntimeError("MCP snapshot escaped the git-excluded output directory: " + str(path))
                snapshot = path.read_text(encoding="utf-8")
            button = re.search(r'button "Smoke" \[ref=([^\]]+)\]', snapshot)
            if not button:
                raise RuntimeError("MCP snapshot did not identify the fixture button: " + snapshot)
            arguments = {"target" if "target" in schemas["browser_click"] else "ref": button[1]}
            if "element" in schemas["browser_click"]:
                arguments["element"] = "Smoke button"
            request("tools/call", dict(name="browser_click", arguments=arguments))
            observed = request("tools/call", dict(name="browser_evaluate", arguments=dict(function="() => document.title")))
            if "42" not in json.dumps(observed):
                raise RuntimeError("MCP did not observe the synthetic button action")
            request("tools/call", dict(name="browser_close", arguments={}))
            result = dict(status="PASS", server=identity.get("serverInfo"), mode="headed" if headed else "headless", synthetic_button_click=True)
            if reports:
                (reports / (name + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result))
        finally:
            site.shutdown()
            web.join(timeout=2)
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                stop_tree(process)
            reader.join(timeout=2)
            process.stdout.close()


def connection_smoke(project, env, command, reports=None):
    mcp_smoke(project, env, None, reports, argv=[*command, "mcp", "--project", str(project), "--headless"], name="mcp-bundled")
    if (project / "ai/ready-check/reports").exists():
        raise RuntimeError("MCP startup created report directories")
    print("Bundled MCP launcher started and kept output excluded")


def save_result(directory, name, process):
    if directory is None:
        return
    (directory / (name + ".log")).write_text(process.stdout + process.stderr, encoding="utf-8")
    try:
        report = json.loads(process.stdout)
    except ValueError:
        return
    (directory / (name + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_logs(directory, source, name):
    if directory is None:
        return
    for log in source.rglob("*.log"):
        if log.name != "setup.log" and name == "setup-logs":
            continue
        destination = directory / name / log.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(log, destination)


def static_smoke(project, root, env, command, reports=None):
    def write(name, content):
        file = project / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")

    write(".gitignore", "vendor/\nnode_modules/\nai/ready-check/\nCLAUDE.local.md\n")
    write("phpstan.neon", "parameters:\n  level: 0\n  paths:\n    - web/modules/custom\n")
    for args in (("init", "-b", "main"), ("add", "."), ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "Fixture")):
        subprocess.run(["git", *args], cwd=project, env=env, check=True, capture_output=True)
    write("vendor/autoload.php", "<?php\n")
    write("web/modules/custom/demo/demo.php", "<?php\nfunction demo_portable() { ready_check_missing(); }\n")
    write("web/modules/custom/demo/demo.js", "readyCheckMissing();\n")
    write("web/modules/custom/demo/demo.scss", ".sample { unknown-property: 1; }\n")
    write("web/modules/custom/demo/demo.info.yml", "name: [broken\n")
    write("web/modules/custom/demo/demo.twig", "{{foo}}\n")
    process = subprocess.run([*command, "static", "--profile", "drupal", "--project", str(project), "--base", "main"],
                             cwd=root, env=env, capture_output=True, encoding="utf-8")
    save_result(reports, "static", process)
    result = json.loads(process.stdout)
    if result.get("evidence_directory"):
        save_logs(reports, Path(result["evidence_directory"]), "static-logs")
    checks = {item["id"]: item for item in result["checks"]}
    print(json.dumps({key: item["status"] for key, item in checks.items()}))
    try:
        if process.returncode != 1 or result["status"] != "FAIL" or result["can_proceed"]:
            raise RuntimeError("Invalid fixture did not block progression")
        for name in ("phpcs", "phpstan", "syntax", "js"):
            if checks[name]["status"] != "FAIL" or not checks[name]["findings"]:
                raise RuntimeError(f"Expected actual {name} findings: {checks[name]}")
        for name in ("twig", "phpmd"):
            if checks[name]["status"] not in {"PASS", "FAIL"}:
                raise RuntimeError(f"Actual {name} did not complete: {checks[name]}")
    except RuntimeError:
        print(process.stdout + process.stderr)
        for log in Path(result["evidence_directory"]).glob("*.log"):
            print(str(log) + "\n" + log.read_text(encoding="utf-8", errors="replace")[-5000:])
        raise


def main():
    parser = argparse.ArgumentParser(description="Exercise real dependency installation and static checker gates.")
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    reports = args.report_dir.resolve() if args.report_dir else None
    if reports:
        if reports.is_relative_to(PLUGIN):
            raise ValueError("Smoke reports must remain outside the plugin repository")
        reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ready check smoke ") as folder:
        root = Path(folder)
        project, data = root / "Drupal site", root / "Managed tools"
        companion = root / "Companion toolkit"
        companion.mkdir()
        (companion / "keep.txt").write_bytes(b"Existing toolkit installation\n")
        for directory in ("bin", "vendor", "composer-home", "composer-cache", "npm-prefix", "npm-cache", "browsers"):
            folder = companion / directory
            folder.mkdir()
            (folder / "keep.txt").write_bytes(b"Do not modify companion tools\n")
        companion_snapshot = {path.relative_to(companion).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in companion.rglob("*") if path.is_file()}
        (project / "web/core/lib").mkdir(parents=True)
        (project / "composer.json").write_text('{"require":{"drupal/core":"^10"}}\n', encoding="utf-8")
        (project / "web/core/lib/Drupal.php").write_text("<?php class Drupal { const VERSION = '10.6.0'; }\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("LINT_", "READY_CHECK_"))}
        env.update(LINT_RUNNER="local", READY_CHECK_DATA_DIR=str(data), PYTHONIOENCODING="utf-8")
        env.update(COMPOSER_BIN_DIR=str(companion / "bin"), COMPOSER_VENDOR_DIR=str(companion / "vendor"),
                   COMPOSER_HOME=str(companion / "composer-home"), COMPOSER_CACHE_DIR=str(companion / "composer-cache"),
                   NPM_CONFIG_PREFIX=str(companion / "npm-prefix"), npm_config_cache=str(companion / "npm-cache"),
                   PLAYWRIGHT_BROWSERS_PATH=str(companion / "browsers"))
        command = [sys.executable, "-B", str(PLUGIN / "scripts/ready-check.py")]
        for attempt in range(2):
            process = subprocess.run([*command, "setup", "--project", str(project)], env=env, capture_output=True, encoding="utf-8")
            save_result(reports, f"setup-{attempt + 1}", process)
            save_logs(reports, data, "setup-logs")
            print(process.stdout)
            if process.returncode:
                for log in data.rglob("setup.log"):
                    print(str(log) + "\n" + log.read_text(encoding="utf-8", errors="replace")[-15000:])
                raise RuntimeError(process.stderr or "Setup failed")
            report = json.loads(process.stdout)
            if report["status"] != "PASS" or any(c["status"] != "PASS" for c in report["components"]):
                raise RuntimeError("Setup did not pass")
            if attempt and any(not c["reused"] for c in report["components"]):
                raise RuntimeError("Repeated setup did not reuse dependencies")
        subprocess.run([*command, "playwright", "--version"], env=env, check=True, cwd=root)
        mcp_smoke(project, env, command, reports)
        connection_smoke(project, env, command, reports)
        if (project / "vendor").exists() or (project / "node_modules").exists():
            raise RuntimeError("Managed dependencies leaked into target project")
        static_smoke(project, root, env, command, reports)
        after_companion = {path.relative_to(companion).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in companion.rglob("*") if path.is_file()}
        if after_companion != companion_snapshot:
            raise RuntimeError("Setup or checking modified the companion toolkit")
        print("Companion toolkit preserved despite inherited package-manager settings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
