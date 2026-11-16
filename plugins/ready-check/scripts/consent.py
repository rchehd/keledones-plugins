#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import settings
from dependency_support import PLUGIN, asset_id, bundle_path, data_root
from detect import detect
from profile_runtime import profile_runner
from project import toplevel, write_json
from setup import install

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


def summary(result, profile, runner):
    parts = []

    for part in result["components"]:
        if part.get("status") != "PASS":
            continue

        if part["component"] == "browser":
            parts.append(f"Playwright CLI {part.get('cli_version')}, MCP {part.get('mcp_version')}, "
                         f"{part.get('browser')} {part.get('browser_version')}")
        else:
            parts.append(f"{profile.capitalize()} checkers in {RUNNERS.get(runner, runner)}")

    return ", ".join(parts)


def browser_log():
    source = PLUGIN / "dependencies/browser"
    log = bundle_path(source, data_root(), "browser") / "setup.log"
    return log if log.is_file() else data_root()


def remember(status, reason=None, log=None):
    write_json(data_root() / "install-result.json",
               dict(status=status, reason=reason, log=str(log) if log else None,
                    bundle=asset_id(PLUGIN / "dependencies/browser")), data_root())


def accept(top, found):
    application = top / found["application"]
    settings.store("install", "auto")
    components = ["browser"]
    later = None

    if found["profile"] and runner_available(application, found["profile"]):
        components.insert(0, "profile")
    elif found["profile"]:
        later = f"{RUNNERS.get(found['runner'], found['runner'])} is not running; the {found['profile'].capitalize()} checkers will install at the first static check."

    result = install(application, found["profile"], tuple(components), say)
    failed = [part for part in result["components"] if part.get("status") != "PASS"]

    if later:
        say(later)

    if failed:
        reasons = "; ".join(f"{part['component']}: {part.get('reason', 'unknown error')}" for part in failed)
        log = browser_log()
        remember("FAIL", reasons, log)
        say(f"Ready Check setup incomplete: {reasons}; log: {log}")
        return 2

    remember("PASS")
    say(f"Ready Check is ready: {summary(result, found['profile'], found['runner'])}")
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Record the Ready Check install decision and project type, then install in the foreground.")
    parser.add_argument("decision", choices=("yes", "no"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--profile")
    parser.add_argument("--runner", choices=sorted(RUNNERS))
    parser.add_argument("--application")
    args = parser.parse_args()

    try:
        top = toplevel(args.project)
        if not top:
            raise ValueError("Ready Check needs a Git work tree")

        found = detect(top)
        found.update({key: value for key, value in (("profile", args.profile), ("runner", args.runner),
                                                     ("application", args.application)) if value})

        if found["profile"] and not settings.valid("profile", found["profile"]):
            say(f"Ready Check has no {found['profile']} profile yet: static checks are unavailable, review and QA work.")
            found["profile"] = None

        if found["profile"]:
            settings.store("profile", found["profile"], top)

        settings.store("runner", found["runner"], top)
        settings.store("application", found["application"], top)

        if args.decision == "no":
            settings.store("install", "never")
            say("Ready Check will not download tools. Review, reminders and task records keep working; "
                "change this later with the setup command.")
            return 0

        return accept(top, found)
    except (OSError, ValueError) as error:
        say(f"Ready Check setup incomplete: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
