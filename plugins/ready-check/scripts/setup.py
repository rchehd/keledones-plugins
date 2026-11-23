#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from process_support import execute, find_command, node_entry
from dependency_support import PLUGIN, asset_files, bundle_path, data_root, installed, outside_repositories, release_lock, take_lock, write_marker
from managed_storage import prepare_storage
from profile_selection import discover
from project import toplevel
from settings import application_root, project_config, store


PHPSTORM_HELP = "https://www.jetbrains.com/help/phpstorm/mcp-server.html"


def enable_phpstorm(project, dry_run, request_id=None):
    top = toplevel(project)
    if not top or top.is_relative_to(PLUGIN):
        raise ValueError("PhpStorm integration needs a project Git work tree")
    if not dry_run:
        store("phpstormMcp", True, top, phpstorm_request_id=request_id)
    status = "PLANNED" if dry_run else "PASS"
    return dict(schema_version=1, action="setup", status=status, components=[
        dict(component="phpstorm", status=status, enabled=True, connection="UNVERIFIED", setup_url=PHPSTORM_HELP)])


def command(argv, cwd, env, timeout):
    code, stdout, stderr = execute(argv, cwd, timeout=timeout, env=env)
    with (cwd / "setup.log").open("ab") as stream:
        stream.write(stdout + stderr + b"\n")
    if code:
        raise ValueError(f"Setup command failed ({code}): {Path(argv[0]).name}; see {cwd / 'setup.log'}")
    return stdout.decode(errors="replace").strip()


def browser_setup(root, project, browser, dry_run, timeout):
    source = PLUGIN / "dependencies/browser"
    destination = bundle_path(source, root, "browser")
    prepare_storage(root, destination, source, "browser", dry_run=True)
    destination = outside_repositories(destination, project)
    cache = outside_repositories(root / "browsers", project)
    details = dict(component="browser", directory=str(destination), browser=browser,
                   host_platform=sys.platform, cli=str(destination / "node_modules/.bin/playwright-cli"),
                   mcp=str(destination / "node_modules/.bin/playwright-mcp"), browser_cache=str(cache))
    if dry_run:
        return dict(status="PLANNED", **details)
    if not find_command("node") or not find_command("npm"):
        raise ValueError("Browser setup needs existing host Node.js 20+ and npm; no system packages are installed")
    code, stdout, _ = execute(["node", "--version"], project)
    if code:
        raise ValueError("Cannot determine host Node.js version")
    node = stdout.decode().strip()
    if int(node.lstrip("v").split(".")[0]) < 20:
        raise ValueError("Browser setup requires host Node.js 20 or newer")
    prepare_storage(root, destination, source, "browser")
    lock = str(destination / ".setup-lock")
    take_lock(lock, timeout)
    try:
        env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(cache), npm_config_cache=str(root / "npm-cache"),
                   npm_config_engine_strict="true")
        for name in ("npm_config_prefix", "NPM_CONFIG_PREFIX", "NODE_PATH", "NODE_OPTIONS"):
            env.pop(name, None)
        reuse = installed(source, destination) and all((destination / "node_modules/.bin" / name).is_file()
                                                      for name in ("playwright-cli", "playwright-mcp")) and (
            destination / "node_modules/axe-core/axe.min.js").is_file() and (
            destination / "node_modules/chart.js/dist/chart.umd.min.js").is_file()
        if not reuse:
            (destination / "ready.json").unlink(missing_ok=True)
            for path in asset_files(source):
                shutil.copyfile(path, destination / path.name)
            command(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], destination, env, timeout)
        cli = node_entry(destination, "@playwright/cli", "playwright-cli")
        cli_version = command(["node", str(cli), "--version"], destination, env, 30)
        expected = json.loads((source / "package.json").read_text(encoding="utf-8"))["dependencies"]["@playwright/cli"]
        if cli_version != expected:
            raise ValueError(f"Installed CLI version {cli_version!r} differs from pinned {expected}")
        mcp = node_entry(destination, "@playwright/mcp", "playwright-mcp")
        mcp_version = command(["node", str(mcp), "--version"], destination, env, 30)
        expected_mcp = json.loads((source / "package.json").read_text(encoding="utf-8"))["dependencies"]["@playwright/mcp"]
        if mcp_version not in {expected_mcp, "Version " + expected_mcp}:
            raise ValueError(f"Installed MCP version {mcp_version!r} differs from pinned {expected_mcp}")
        command(["node", "node_modules/playwright-core/cli.js", "install", browser], destination, env, timeout)
        probe = ("const {" + browser + "} = require('playwright-core'); "
                 "(async () => { const b = await " + browser + ".launch({headless:true}); "
                 "try { const p = await b.newPage(); await p.setContent('<title>Ready Check setup</title>'); "
                 "if (await p.title() !== 'Ready Check setup') throw Error('Browser smoke check failed'); "
                 "console.log(await b.version()); } finally { await b.close(); } })().catch(e => { console.error(e); process.exit(1); });")
        browser_version = command(["node", "-e", probe], destination, env, 45)
        axe = destination / "node_modules/axe-core"
        if not (axe / "axe.min.js").is_file():
            raise ValueError("axe-core is missing from the browser bundle")
        axe_version = json.loads((axe / "package.json").read_text(encoding="utf-8"))["version"]
        chart = destination / "node_modules/chart.js"
        if not (chart / "dist/chart.umd.min.js").is_file():
            raise ValueError("chart.js is missing from the browser bundle")
        chart_version = json.loads((chart / "package.json").read_text(encoding="utf-8"))["version"]
        details.update(node=node, cli_version=cli_version, mcp_version=expected_mcp, browser_version=browser_version,
                       axe_version=axe_version, chart_version=chart_version, reused=reuse)
        write_marker(source, destination, details)
        return dict(status="PASS", **details)
    finally:
        release_lock(lock)


def profile_setup(project, root, profile_id, runner_data_dir, dry_run, timeout):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", profile_id):
        raise ValueError("Invalid profile ID")

    folder = PLUGIN / "profiles" / profile_id
    profile = json.loads((folder / "profile.json").read_text(encoding="utf-8"))

    if profile.get("schema_version") != 1 or profile.get("id") != profile_id:
        raise ValueError("Unsupported profile manifest")

    project_config(project, profile_id)

    entry = (folder / profile["scripts"]["setup"]).resolve(strict=True)

    if not entry.is_relative_to(folder.resolve()) or entry.suffix != ".py":
        raise ValueError("Setup entry point must be Python inside the selected profile")

    spec = importlib.util.spec_from_file_location("ready_check_profile_setup", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    part = module.setup(project, root, runner_data_dir, dry_run, timeout)
    allowed = {"PLANNED", "INCOMPLETE"} if dry_run else {"PASS", "INCOMPLETE"}

    if not isinstance(part, dict) or part.get("component") != profile_id or part.get("status") not in allowed:
        raise ValueError("Profile setup returned an invalid component result")

    return part


def install(project, profile, components, progress=lambda message: None, browser="chromium", root=None,
            runner_data_dir=None, dry_run=False, timeout=900):
    project = Path(project).resolve(strict=True)

    if not project.is_dir() or timeout <= 0:
        raise ValueError("A project directory and positive timeout are required")

    if "profile" in components and profile and not (PLUGIN / "profiles" / profile / "profile.json").is_file():
        raise ValueError(f"Unknown profile: {profile}")

    root = outside_repositories(Path(root or data_root()).expanduser().resolve(), project)
    result = dict(schema_version=1, action="setup", status="INCOMPLETE", data_directory=str(root), components=[])

    if "profile" in components and profile:
        progress(f"Preparing {profile.capitalize()} checks…")

        try:
            result["components"].append(profile_setup(project, root, profile, runner_data_dir, dry_run, timeout))
        except (OSError, ValueError, KeyError, ImportError, subprocess.SubprocessError) as error:
            result["components"].append(dict(component=profile, status="INCOMPLETE", reason=str(error)))

    if "browser" in components:
        progress("Installing Playwright CLI, Playwright MCP and the browser…")

        try:
            result["components"].append(browser_setup(root, project, browser, dry_run, timeout))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            result["components"].append(dict(component="browser", status="INCOMPLETE", reason=str(error)))

    statuses = {part["status"] for part in result["components"]}
    result["status"] = "INCOMPLETE" if "INCOMPLETE" in statuses or not statuses else "PLANNED" if dry_run else "PASS"
    return result


def install_selected(top, selections, components, progress=lambda message: None, browser="chromium", root=None,
                     runner_data_dir=None, dry_run=False, timeout=900):
    if timeout <= 0:
        raise ValueError("A positive timeout is required")
    root = outside_repositories(Path(root or data_root()).expanduser().resolve(), top)
    result = dict(schema_version=1, action="setup", status="INCOMPLETE", data_directory=str(root), components=[])
    for item in selections if "profile" in components else []:
        profile, application = item["profile"], item["application"]
        project = application_root(top, application)
        progress(f"Preparing {profile.capitalize()} checks in {application}…")
        argv = [sys.executable, str(Path(__file__).resolve()), "--project", str(project), "--profile", profile,
                "--component", "profile", "--data-dir", str(root), "--timeout", str(timeout)]
        if runner_data_dir:
            argv += ["--runner-data-dir", runner_data_dir]
        if dry_run:
            argv.append("--dry-run")
        try:
            process = subprocess.run(argv, capture_output=True, encoding="utf-8", cwd=project)
            child = json.loads(process.stdout)
            if process.returncode not in {0, 2} or len(child["components"]) != 1:
                raise ValueError(child.get("reason") or process.stderr.strip() or "Profile setup returned no result")
            part, = child["components"]
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            part = dict(component=profile, status="INCOMPLETE", reason=str(error))
        result["components"].append(dict(part, application=application, runner=part.get("runner", item["runner"])))

    if "browser" in components:
        shared = install(top, None, ("browser",), progress, browser, root, dry_run=dry_run, timeout=timeout)
        result["components"].extend(shared["components"])

    statuses = {part["status"] for part in result["components"]}
    if statuses and "INCOMPLETE" not in statuses:
        result["status"] = "PLANNED" if dry_run else "PASS"
    return result


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Install Ready Check browser tools and framework-profile checkers outside the project.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--profile")
    parser.add_argument("--component", choices=("all", "browser", "profile", "phpstorm"), default="all")
    parser.add_argument("--phpstorm-request", help="Complete the pending PhpStorm connection with this request ID")
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    parser.add_argument("--data-dir", type=Path, default=data_root())
    parser.add_argument("--runner-data-dir")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    components = ("browser", "profile") if args.component == "all" else (args.component,)

    try:
        if args.phpstorm_request is not None and args.component != "phpstorm":
            raise ValueError("--phpstorm-request requires --component phpstorm")
        options = dict(browser=args.browser, root=args.data_dir, runner_data_dir=args.runner_data_dir,
                       dry_run=args.dry_run, timeout=args.timeout)
        if args.component == "phpstorm":
            result = enable_phpstorm(args.project, args.dry_run, args.phpstorm_request)
        elif args.profile or "profile" not in components:
            result = install(args.project, args.profile, components, **options)
        else:
            top, selected, conflicts = discover(args.project)
            if conflicts:
                raise ValueError("Several profiles match the same application; use profiles and confirm selections first")
            if not selected:
                raise ValueError("No configured profile for the requested scope")
            result = install_selected(top, selected, components, **options)
    except (OSError, ValueError) as error:
        result = dict(schema_version=1, action="setup", status="INCOMPLETE", components=[], reason=str(error))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PASS", "PLANNED"} else 2


if __name__ == "__main__":
    sys.exit(main())
