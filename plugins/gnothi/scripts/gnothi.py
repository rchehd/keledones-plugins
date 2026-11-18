#!/usr/bin/env python3
"""Gnothi command line."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import digest  # noqa: E402
import profiles  # noqa: E402
import report  # noqa: E402
from report_strings import ENGLISH  # noqa: E402
import storage  # noqa: E402
from sessions import PERIODS  # noqa: E402
from sources import ADAPTERS, chat_history  # noqa: E402


def sources(args):
    found = []

    for adapter in ADAPTERS:
        base = adapter.root()
        paths = adapter.files(base)
        found.append({"client": adapter.CLIENT, "root": str(base), "found": bool(paths), "files": len(paths)})

    if args:
        _, imports = chat_history.import_sources(args.chat_export, args.chat_sample)
        found.extend(imports)

    return {"sources": found}


def collect(args):
    try:
        options = profiles.read()["options"]
    except storage.StoragePermissionError:
        if not args.no_save:
            raise
        options = dict(profiles.OPTIONS, metrics_only=True)

    period = args.period or options["period"]
    data = digest.build(period, digest.date.today(), args.budget, args.metrics_only or options["metrics_only"],
                        args.archetypes or options["archetypes"], args.chat_export, args.chat_sample,
                        use_cache=not args.no_save)
    if args.no_save:
        return data

    profiles.set_options(period=period)
    path = storage.write_private(storage.data_root() / "tmp/digest.json", json.dumps(data, ensure_ascii=False, indent=1))
    return dict(data, digest=str(path))


def profile(args):
    if args.profile_command == "templates":
        return {"templates": profiles.templates()}

    if args.profile_command == "set":
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
        profiles.set_axes(data.get("axes"), str(data.get("description") or ""), data.get("template"))
    elif args.profile_command == "options":
        changes = {key: getattr(args, key) == "on" for key in ("archetypes", "metrics_only") if getattr(args, key)}

        if args.period:
            changes["period"] = args.period

        profiles.set_options(**changes)

    current = profiles.read()
    return {"profile": current, "epoch": profiles.current_epoch(current), "data_root": str(storage.data_root())}


def render(args):
    return report.render(args.portrait)


def forget(args):
    if not args.yes:
        raise ValueError("forget deletes all Gnothi data; run it again with --yes after the user confirms")

    return {"removed": str(storage.forget())}


def parser():
    root = argparse.ArgumentParser(prog="gnothi", description="Gnothi: a private portrait of how you work with AI agents.")
    commands = root.add_subparsers(dest="command", required=True)
    source_command = commands.add_parser("sources", help="List readable session folders and supplied chat history")
    source_command.set_defaults(run=sources)
    commands.add_parser("storage-check", help="Check writes to the private data directory").set_defaults(
        run=lambda _: {"data_root": str(storage.check_writable())})
    command = commands.add_parser("collect", help="Build the redacted digest for one period")
    command.add_argument("--period", choices=list(PERIODS))
    command.add_argument("--budget", type=int, default=30000)
    command.add_argument("--metrics-only", action="store_true")
    command.add_argument("--archetypes", action="store_true")
    command.add_argument("--no-save", action="store_true", help="Print the digest without updating local storage")
    command.set_defaults(run=collect)
    for reader in (source_command, command):
        reader.add_argument("--chat-export", action="append", default=[], metavar="PATH",
                            help="Read an official ChatGPT or Claude JSON/ZIP export; repeat for multiple exports")
        reader.add_argument("--chat-sample", action="append", default=[], metavar="PATH",
                            help="Read retrieved chat messages in Gnothi JSON format; use - for stdin")
    command = commands.add_parser("profile", help="Show or change the profile and options")
    actions = command.add_subparsers(dest="profile_command", required=True)
    actions.add_parser("show")
    actions.add_parser("templates")
    actions.add_parser("set").add_argument("--file", required=True)
    options = actions.add_parser("options")
    options.add_argument("--archetypes", choices=("on", "off"))
    options.add_argument("--metrics-only", choices=("on", "off"))
    options.add_argument("--period", choices=list(PERIODS))
    command.set_defaults(run=profile)
    command = commands.add_parser("render", help="Validate portrait.json and write the HTML report")
    command.add_argument("--portrait")
    command.set_defaults(run=render)
    commands.add_parser("ui-strings", help="List report strings and placeholders for translation").set_defaults(
        run=lambda _: {"strings": ENGLISH})
    command = commands.add_parser("forget", help="Delete all Gnothi data")
    command.add_argument("--yes", action="store_true")
    command.set_defaults(run=forget)
    return root


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parser().parse_args(argv)
    result = {"schema_version": 1, "action": args.command, "status": "FAIL"}

    try:
        result.update(args.run(args))
        result["status"] = "PASS"
    except storage.StoragePermissionError as error:
        result.update(reason=str(error), error_code="storage_access_denied", path=str(error.path))
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
