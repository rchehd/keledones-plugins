#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
from dependency_support import PLUGIN, bundle_path, data_root, installed
from git_exclude import git
from process_support import execute, find_command, node_entry
from project import BASE, ensure_excluded, migrate, toplevel

OUTPUT = BASE / "tmp/playwright-mcp"


def command(project, browser, headless):
    source = PLUGIN / "dependencies/browser"
    root = data_root()
    folder = bundle_path(source, root, "browser")
    if not installed(source, folder):
        raise ValueError("Ready Check browser tools are not installed; run the consent/setup command")
    binary = node_entry(folder, "@playwright/mcp", "playwright-mcp")
    node = find_command("node")
    if not node:
        raise ValueError("Playwright MCP requires host Node.js 20+")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("PLAYWRIGHT_MCP_") and key not in {"NODE_OPTIONS", "NODE_PATH"}}
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(root / "browsers")
    code, output, error = execute([node, "-e", "process.stdout.write(require('playwright-core')[process.argv[1]].executablePath())", browser],
                                  folder, env=env)
    if code:
        raise ValueError("Cannot resolve the managed browser: " + error.decode(errors="replace"))
    executable = output.decode("utf-8")
    if not Path(executable).is_file():
        raise ValueError("Managed browser executable is missing; repeat ready:setup")
    output = output_directory(project)
    config = output / f"config-{browser}-{'headless' if headless else 'headed'}.json"
    axe = folder / "node_modules/axe-core/axe.min.js"
    settings = dict(browserName=browser, isolated=True, launchOptions=dict(headless=headless, executablePath=executable))
    if axe.is_file():
        # Exposes window.axe for the accessibility check; nothing runs until QA calls axe.run().
        settings["initScript"] = [str(axe)]
    write_atomic(config, json.dumps(dict(browser=settings, outputDir=str(output), capabilities=["devtools"], webmcp=False)))
    return node, [node, str(binary), "--config", str(config)], env, project


def output_directory(project):
    if project.is_relative_to(PLUGIN):
        raise ValueError("Playwright MCP requires an application directory outside the plugin package")
    top = toplevel(project)

    if not top:
        fallback = data_root() / "state" / "playwright-mcp"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    migrate(top)
    ensure_excluded(top)
    if git(top, "check-ignore", "-q", "--", OUTPUT.as_posix() + "/") is None:
        raise ValueError(f"Playwright MCP output directory must be ignored by Git: {top / OUTPUT}")
    current = top
    for part in OUTPUT.parts:
        current = current / part
        if current.resolve() != current or current.exists() and not current.is_dir():
            raise ValueError(f"MCP output path must contain real directories: {current}")
        current.mkdir(exist_ok=True)
    return current


def write_atomic(path, text):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".config.", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(text)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def launch(node, argv, env, project):
    os.chdir(project)
    if os.name == "nt":
        return subprocess.run(argv, env=env).returncode
    os.execvpe(node, argv, env)


def main():
    parser = argparse.ArgumentParser(description="Run the installed official Playwright MCP over stdio; never installs packages.")
    parser.add_argument("--project", type=Path, default=Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headed", action="store_true")
    mode.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    try:
        return launch(*command(args.project.resolve(strict=True), args.browser, args.headless and not args.headed))
    except (OSError, ValueError) as error:
        print(f"Cannot start Ready Check Playwright MCP: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
