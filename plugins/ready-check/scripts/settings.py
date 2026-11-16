#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
import logs
from dependency_support import PLUGIN, data_root
from project import BASE, ensure_excluded, toplevel, write_json

DEFAULTS = {"browser": "ask", "install": "ask", "captureTasks": True, "remind": True, "artifactLanguage": "English"}
CHOICES = {"browser": {"ask", "visible", "background"}, "install": {"ask", "auto", "never"},
           "runner": {"local", "ddev", "compose"}}
BOOLEAN = {"captureTasks", "remind"}
USER_ONLY = {"install"}
PROJECT_ONLY = {"profile", "runner", "application"}
KEYS = set(DEFAULTS) | PROJECT_ONLY


def user_path():
    return data_root() / "settings.json"


def project_path(top):
    return Path(top) / BASE / "settings.json"


def valid(key, value):
    if key in BOOLEAN:
        return isinstance(value, bool)

    if key in CHOICES:
        return value in CHOICES[key]

    if key == "profile":
        return (isinstance(value, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is not None and
                (PLUGIN / "profiles" / value / "profile.json").is_file())

    if key == "artifactLanguage":
        return isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z -]{1,39}", value) is not None

    if key == "application":
        path = PurePosixPath(value) if isinstance(value, str) else None
        return path is not None and not path.is_absolute() and ".." not in path.parts and "\\" not in value

    return False


def read(path):
    try:
        if not path.is_file():
            return {}

        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("settings must be a JSON object")

        return data
    except (OSError, ValueError) as error:
        logs.error(f"Ignoring unreadable settings {path}: {error}")
        return {}


def load(top=None):
    result = dict(DEFAULTS)
    sources = [(user_path(), KEYS - PROJECT_ONLY)]

    if top:
        sources.append((project_path(top), KEYS - USER_ONLY))

    for path, allowed in sources:
        for key, value in read(path).items():
            if key in allowed and valid(key, value):
                result[key] = value
            else:
                logs.error(f"Ignoring setting {key}={value!r} in {path}")

    return result


def store(key, value, top=None):
    if key not in KEYS:
        raise ValueError(f"Unknown setting: {key}")

    if not valid(key, value):
        raise ValueError(f"Invalid value for {key}: {value!r}")

    if key in PROJECT_ONLY and not top:
        raise ValueError(f"{key} is a project setting; pass --project")

    project = bool(top) and key not in USER_ONLY
    path = project_path(top) if project else user_path()
    data = read(path)
    data[key] = value
    write_json(path, data, Path(top) if project else data_root())

    if project:
        ensure_excluded(Path(top))


def project_config(application):
    application = Path(application)
    path = application / ".ready-check.json"
    config = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    if not isinstance(config, dict):
        raise ValueError("Project configuration must be an object")

    top = toplevel(application)
    stored = read(project_path(top)) if top else {}
    config.update({key: stored[key] for key in ("profile", "runner") if valid(key, stored.get(key))})
    return config


def parse(value):
    return {"true": True, "false": False}.get(value.lower(), value)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Read or change Ready Check settings.")
    parser.add_argument("operation", choices=("get", "set"))
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--project", type=Path)
    args = parser.parse_args()
    result = dict(schema_version=1, action="config", status="FAIL")

    try:
        top = None

        if args.project:
            top = toplevel(args.project)
            if not top:
                raise ValueError("Project settings need a Git work tree")

        if args.key is not None and args.key not in KEYS:
            raise ValueError(f"Unknown setting: {args.key}")

        if args.operation == "set":
            if args.key is None or args.value is None:
                raise ValueError("config set needs a key and a value")
            store(args.key, parse(args.value), top)

        values = load(top)
        result.update(status="PASS", settings={args.key: values.get(args.key)} if args.key else values)
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
