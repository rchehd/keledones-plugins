#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import logs
from dependency_support import data_root
from project import BASE, ensure_excluded, toplevel

LIMIT = 4 * 1024
TEAM = BASE / "rules.md"
# Claude Code exports userConfig "rules"; Cursor plugin variables and manual setups use READY_CHECK_RULES.
ENVIRONMENT = ("CLAUDE_PLUGIN_OPTION_RULES", "READY_CHECK_RULES")


def user_path():
    return data_root() / "rules.md"


def team_path(top):
    return Path(top) / TEAM


def item_hash(text):
    text = re.sub(r"^\s*[-*]\s*(\[[ xX]\]\s*)?", "", text)
    text = re.sub(r"^MUST:\s*", "", text.strip(), flags=re.I)
    return hashlib.sha256(" ".join(text.lower().split()).encode("utf-8")).hexdigest()[:16]


def disabled_path(top=None):
    return (Path(top) / BASE if top else data_root()) / "disabled.json"


def disabled_hashes(top=None):
    found = set()

    for path in [disabled_path()] + ([disabled_path(top)] if top else []):
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            found.update(item for item in data.get("hashes", []) if isinstance(item, str))
        except (OSError, ValueError, AttributeError, TypeError) as error:
            logs.error(f"Ignoring unreadable disabled list {path}: {error}")

    return found


def parse_lines(text):
    found = []

    for line in text.splitlines():
        line = line.strip()

        if not line or line.startswith(("#", "<!--")):
            continue

        found.append(line[2:].strip() if line.startswith(("- ", "* ")) else line)

    return [line for line in found if line]


def parse_environment(value):
    value = value.strip()

    if value.startswith("["):
        try:
            items = json.loads(value)
            return [str(item).strip() for item in items if str(item).strip()]
        except ValueError:
            pass

    return parse_lines(value)


def read_file(path):
    try:
        return parse_lines(path.read_text(encoding="utf-8-sig")) if path.is_file() else []
    except (OSError, ValueError) as error:
        logs.error(f"Ignoring unreadable rules {path}: {error}")
        return []


def load(top=None):
    sources = [("client settings", rule) for name in ENVIRONMENT for rule in parse_environment(os.environ.get(name, ""))]
    sources += [("user", rule) for rule in read_file(user_path())]

    if top:
        sources += [("team", rule) for rule in read_file(team_path(top))]

    rules, seen = [], set()
    disabled = disabled_hashes(top)

    for source, text in sources:
        if item_hash(text) in disabled:
            continue

        must = text.upper().startswith("MUST:")
        body = text[5:].strip() if must else text

        if body and body.lower() not in seen:
            seen.add(body.lower())
            rules.append(dict(source=source, must=must, text=body))

    return rules


def context(top=None):
    rules = load(top)

    if not rules:
        return None

    lines = [f"- {'MUST: ' if rule['must'] else ''}{rule['text']} ({rule['source']})" for rule in rules]
    text = ("Ready Check coding rules from the user and team. Follow them when writing code; the Ready Check review "
            "checks changed code against them (MUST rules block, others are recommendations):\n" + "\n".join(lines))
    encoded = text.encode("utf-8")

    if len(encoded) > LIMIT:
        text = encoded[:LIMIT].decode("utf-8", "ignore").rsplit("\n", 1)[0] + "\n- (more rules omitted: over 4 KB)"

    return text


def add(text, top=None, must=False):
    text = " ".join(text.split())

    if not text:
        raise ValueError("Rule text is empty")

    path = team_path(top) if top else user_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_symlink():
        raise ValueError(f"Refusing to write rules through a symlink: {path}")

    content = path.read_bytes() if path.is_file() else b""
    prefix = "\n" if content and not content.endswith(b"\n") else ""

    with open(path, "a", encoding="utf-8") as stream:
        stream.write(f"{prefix}- {'MUST: ' if must else ''}{text}\n")

    if top:
        ensure_excluded(Path(top))

    return path


def remove(text, top=None):
    path = team_path(top) if top else user_path()

    if not path.is_file():
        raise ValueError(f"No rules file: {path}")

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if text.lower() not in line.lower()]

    if len(kept) == len(lines):
        raise ValueError(f"No rule matches: {text}")

    path.write_text("".join(kept), encoding="utf-8")

    if top:
        ensure_excluded(Path(top))

    return path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="List, add or remove Ready Check coding rules.")
    parser.add_argument("operation", choices=("list", "add", "remove"))
    parser.add_argument("text", nargs="?")
    parser.add_argument("--project", type=Path, help="With add/remove: change the team file in the repository")
    parser.add_argument("--must", action="store_true", help="With add: violations block the review")
    args = parser.parse_args()
    result = dict(schema_version=1, action="rules", status="FAIL")

    try:
        top = toplevel(args.project) if args.project else None

        if args.project and not top:
            raise ValueError("Team rules need a Git work tree")

        if args.operation != "list" and not args.text:
            raise ValueError(f"rules {args.operation} needs the rule text")

        if args.operation == "add":
            result["file"] = str(add(args.text, top, args.must))
        elif args.operation == "remove":
            result["file"] = str(remove(args.text, top))

        result.update(status="PASS", rules=load(top), user_file=str(user_path()),
                      team_file=str(team_path(top)) if top else None)
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
