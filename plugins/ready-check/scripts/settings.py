#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

sys.dont_write_bytecode = True
import logs
from dependency_support import PLUGIN, data_root
from project import BASE, LEGACY_BASE, ensure_excluded, migrate, migration_lock, project_file, toplevel, write_json

DEFAULTS = {"browser": "ask", "install": "ask", "captureTasks": True, "remind": True, "artifactLanguage": "English"}
CHOICES = {"browser": {"ask", "visible", "background"}, "install": {"ask", "auto", "never"},
           "runner": {"local", "ddev", "compose"}}
BOOLEAN = {"captureTasks", "remind"}
USER_ONLY = {"install"}
SCALAR_SELECTION = {"profile", "runner", "application"}
PROJECT_ONLY = SCALAR_SELECTION | {"profiles"}
TEMPLATE_KEYS = {"commitTemplate", "pullRequestTemplate", "taskCommentTemplate"}
KEYS = set(DEFAULTS) | PROJECT_ONLY | TEMPLATE_KEYS


def user_path():
    return data_root() / "settings.json"


def project_path(top):
    return Path(top) / BASE / "settings.json"


def valid(key, value):
    if key in TEMPLATE_KEYS:
        return isinstance(value, str) and bool(value.strip()) and all(character.isprintable() for character in value)

    if key in BOOLEAN:
        return isinstance(value, bool)

    if key in CHOICES:
        return isinstance(value, str) and value in CHOICES[key]

    if key == "profile":
        return (isinstance(value, str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) is not None and
                (PLUGIN / "profiles" / value / "profile.json").is_file())

    if key == "artifactLanguage":
        return isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z ()-]{1,39}", value) is not None

    if key == "application":
        path = PurePosixPath(value) if isinstance(value, str) else None
        return (path is not None and bool(value) and path.as_posix() == value and not path.is_absolute()
                and not PureWindowsPath(value).drive and ".." not in path.parts and "\\" not in value
                and all(character.isprintable() for character in value))

    if key == "profiles":
        if not isinstance(value, list) or not value:
            return False
        keys = set()
        for item in value:
            if not isinstance(item, dict) or item.keys() != SCALAR_SELECTION:
                return False
            if not all(valid(field, entry) for field, entry in item.items()):
                return False
            identity = item["application"], item["profile"]
            if identity in keys:
                return False
            keys.add(identity)
        return True

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
        sources.append((project_file(top, "settings.json"), KEYS - USER_ONLY))

    for path, allowed in sources:
        for key, value in read(path).items():
            if key in allowed and valid(key, value):
                result[key] = value
            else:
                logs.error(f"Ignoring setting {key}={value!r} in {path}")

    return result


def setting_location(key, top):
    if key not in KEYS:
        raise ValueError(f"Unknown setting: {key}")

    if key in PROJECT_ONLY and not top:
        raise ValueError(f"{key} is a project setting; pass --project")

    if top and key not in USER_ONLY:
        return project_path(top), Path(top)
    return user_path(), data_root()


def template_path(value, top=None):
    try:
        path = Path(value).expanduser()
        resolved = (top / path if top else path).resolve()
        if top and resolved.is_relative_to(top / LEGACY_BASE) and not resolved.exists():
            resolved = (top / BASE / resolved.relative_to(top / LEGACY_BASE)).resolve()
    except RuntimeError as error:
        raise ValueError(f"Cannot resolve template path {value!r}: {error}") from error
    if top and not resolved.is_relative_to(top):
        raise ValueError("A project template must be inside the repository")
    return resolved


def store(key, value, top=None):
    path, root = setting_location(key, top)
    if not valid(key, value):
        raise ValueError(f"Invalid value for {key}: {value!r}")
    if key in TEMPLATE_KEYS:
        source = template_path(value, top)
        if not source.is_file():
            raise ValueError(f"Template file does not exist: {source}")
        value = source.relative_to(top).as_posix() if top else str(source)

    project = top and key not in USER_ONLY
    if project:
        migrate(top)
        ensure_excluded(top)
    with migration_lock(path.parent):
        data = read(project_file(top, path.name) if project else path)
        if key == "profiles":
            for item in value:
                application_root(top, item["application"])
            for field in SCALAR_SELECTION:
                data.pop(field, None)
        elif key in SCALAR_SELECTION and "profiles" in data:
            raise ValueError("Replace the profiles list to change a configured selection")
        data[key] = value
        write_json(path, data, root)


def unset(key, top=None):
    path, root = setting_location(key, top)
    project = top and key not in USER_ONLY
    if project:
        migrate(top)
        ensure_excluded(top)
    with migration_lock(path.parent):
        data = read(project_file(top, path.name) if project else path)
        if key in data:
            del data[key]
            write_json(path, data, root)


def shared_config(application):
    application = Path(application)
    path = application / ".ready-check.json"
    config = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}

    if not isinstance(config, dict):
        raise ValueError("Project configuration must be an object")

    return config


def configured_profiles(top):
    shared = shared_config(top)
    stored = read(project_file(top, "settings.json"))
    for config in (stored, shared):
        if "profiles" in config:
            if not valid("profiles", config["profiles"]):
                raise ValueError("Invalid profiles list in project configuration")
            return config["profiles"]
        if "profile" in config:
            from detect import profile_runner_name
            legacy = shared | stored
            profile = legacy["profile"]
            application = legacy.get("application", ".")
            if isinstance(application, str):
                application = PurePosixPath(application).as_posix()
            if not valid("profile", profile) or not valid("application", application):
                raise ValueError("Invalid profile or application in project configuration")
            selected_runner = legacy.get("runner") or profile_runner_name(profile, top, top / application)
            if not valid("runner", selected_runner):
                raise ValueError("Invalid runner in project configuration")
            return [dict(profile=profile, application=application, runner=selected_runner)]
    return []


def application_root(top, application):
    if not valid("application", application):
        raise ValueError(f"Invalid application root: {application!r}")
    path = (top / application).resolve()
    if not path.is_relative_to(top) or not path.is_dir() or path != top / application:
        raise ValueError(f"Application must be a directory inside the project: {application}")
    return path


def project_config(application, profile=None):
    application = Path(application).resolve()
    config = shared_config(application)
    top = toplevel(application)
    selections = configured_profiles(top or application)

    if selections:
        relative = application.relative_to(top or application).as_posix()
        matching = [item for item in selections if item["application"] == relative
                    and (profile is None or item["profile"] == profile)]
        if profile is not None and not matching:
            raise ValueError("Selected profile and application conflict with project configuration")
        if len(matching) == 1:
            config.update(matching[0])
    elif top:
        stored = read(project_file(top, "settings.json"))
        if "runner" not in config:
            runner = (shared_config(top) | stored).get("runner")
            if valid("runner", runner):
                config["runner"] = runner

    if profile is not None and config.get("profile", profile) != profile:
        raise ValueError("Selected profile conflicts with project configuration")
    return config


def parse(value):
    return {"true": True, "false": False}.get(value.lower(), value)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Read or change Ready Check settings.")
    parser.add_argument("operation", choices=("get", "set", "unset"))
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
            if args.key == "profiles":
                value = json.loads(args.value)
            else:
                value = args.value if args.key in TEMPLATE_KEYS else parse(args.value)
            store(args.key, value, top)
        elif args.operation == "unset":
            if args.key is None or args.value is not None:
                raise ValueError("config unset needs one key")
            unset(args.key, top)

        values = load(top)
        result.update(status="PASS", settings={args.key: values.get(args.key)} if args.key else values)
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
