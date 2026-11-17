#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import settings
from dependency_support import PLUGIN, asset_id, bundle_path, data_root
from detect import FALLBACK, runner
from profile_runtime import profile_runner
from profile_selection import discover, parse_argument, selection
from project import toplevel, write_json
from setup import install_selected

RUNNERS = {"ddev": "DDEV", "compose": "Docker Compose", "local": "local"}


def say(message):
    print(message, flush=True)


def runner_available(application, profile):
    if not profile:
        return False

    try:
        return profile_runner(application, profile)[0].available()
    except (ImportError, OSError, ValueError):
        return False


def summary(result):
    parts = []

    for part in result["components"]:
        if part.get("status") != "PASS":
            continue

        if part["component"] == "browser":
            parts.append(f"Playwright CLI {part.get('cli_version')}, MCP {part.get('mcp_version')}, "
                         f"{part.get('browser')} {part.get('browser_version')}")
        else:
            runner_name = part["runner"]
            parts.append(f"{part['component'].capitalize()} checks in {part['application']} ({RUNNERS.get(runner_name, runner_name)})")

    return ", ".join(parts)


def browser_log():
    source = PLUGIN / "dependencies/browser"
    log = bundle_path(source, data_root(), "browser") / "setup.log"
    return log if log.is_file() else data_root()


def remember(status, reason=None, log=None):
    write_json(data_root() / "install-result.json",
               dict(status=status, reason=reason, log=str(log) if log else None,
                    bundle=asset_id(PLUGIN / "dependencies/browser")), data_root())


def accept(top, selected):
    settings.store("install", "auto")
    available = []
    for item in selected:
        profile, name, application = item["profile"], item["runner"], item["application"]
        if profile == FALLBACK or runner_available(top / application, profile):
            available.append(item)
        else:
            say(f"{RUNNERS[name]} is unavailable for {profile.capitalize()} in {application}. "
                "Its checkers will install at the first static check with a working runner.")

    result = install_selected(top, available, ("profile", "browser"), say)
    failed = [part for part in result["components"] if part.get("status") != "PASS"]
    browser = next(part for part in result["components"] if part["component"] == "browser")
    if browser["status"] == "PASS":
        remember("PASS")
    else:
        remember("FAIL", browser.get("reason"), browser_log())
    if failed:
        reasons = "; ".join(f"{part['component']} ({part.get('application', '.')}): "
                            f"{part.get('reason', 'unknown error')}" for part in failed)
        say(f"Ready Check setup incomplete: {reasons}")
        return 2

    say(f"Ready Check is ready: {summary(result)}")
    return 0


def confirmed_selections(top, args):
    if args.selection:
        if args.profile or args.runner or args.application:
            raise ValueError("Use --selection or the single-profile flags")
        return [parse_argument(value) for value in args.selection]

    if args.profile and args.application is not None:
        application = settings.application_root(top, args.application)
        name = args.runner or ("local" if args.profile == FALLBACK else runner(application, application))
        return [dict(profile=args.profile, application=args.application, runner=name)]

    _, candidates, conflicts = discover(args.project)
    if args.profile:
        matching = [item for item in candidates if item["profile"] == args.profile]
        if len(matching) > 1:
            raise ValueError("The profile matches several applications; pass --application")
        if matching:
            return [dict(selection(matching[0]), runner=args.runner or matching[0]["runner"])]
        application = args.project.resolve()
        name = args.runner or ("local" if args.profile == FALLBACK else runner(application, application))
        return [dict(profile=args.profile, application=application.relative_to(top).as_posix(), runner=name)]

    if args.application is not None:
        settings.application_root(top, args.application)
        candidates = [item for item in candidates if item["application"] == args.application]
        conflicts = [item for item in conflicts if item["application"] == args.application]
    if conflicts:
        raise ValueError("Several profiles match the same application; pass the confirmed --selection entries")
    return [dict(selection(item), runner=args.runner or item["runner"]) for item in candidates]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Record the Ready Check install decision and project type, then install in the foreground.")
    parser.add_argument("decision", choices=("yes", "no"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--profile")
    parser.add_argument("--runner", choices=sorted(RUNNERS))
    parser.add_argument("--application")
    parser.add_argument("--selection", action="append", metavar="PROFILE:RUNNER:APPLICATION")
    args = parser.parse_args()

    try:
        top = toplevel(args.project)
        if not top:
            raise ValueError("Ready Check needs a Git work tree")

        selected = confirmed_selections(top, args)
        if not settings.valid("profiles", selected):
            raise ValueError("Expected unique selections with a packaged profile, runner and application")
        settings.store("profiles", selected, top)

        if args.decision == "no":
            settings.store("install", "never")
            say("Ready Check will not download tools. Review, reminders and task records keep working; "
                "change this later with the setup command.")
            return 0

        return accept(top, selected)
    except (OSError, ValueError) as error:
        say(f"Ready Check setup incomplete: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
