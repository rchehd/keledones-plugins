#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import rules
from dependency_support import data_root
from project import BASE, ensure_excluded, toplevel, write_json

KINDS = ("rule", "review", "qa")
SCOPES = ("project", "global")
ITEM = re.compile(r"^\s*[-*]\s+(\[[ xX]\]\s+)?(?P<text>.+?)\s*$")


def base(scope, top):
    if scope == "project":
        if not top:
            raise ValueError("Project scope needs a Git work tree; pass --project")
        return Path(top) / BASE

    return data_root()


def file_for(kind, scope, top, profile):
    if kind == "rule":
        return base(scope, top) / "rules.md"

    if not profile or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", profile):
        raise ValueError("Review and QA items need a valid --profile")

    return base(scope, top) / "extensions" / profile / f"{kind}.md"


def parse_extension(path):
    section, items = "General", []

    if not path.is_file():
        return items

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue

        match = ITEM.match(line)

        if match:
            items.append((section, match.group("text")))

    return items


def load(top=None, kind=None, profile=None):
    disabled = rules.disabled_hashes(top)
    found = []

    for wanted in [kind] if kind else KINDS:
        if wanted == "rule":
            sources = [("client settings", None, text) for name in rules.ENVIRONMENT
                       for text in rules.parse_environment(os.environ.get(name, ""))]
            sources += [("global", rules.user_path(), text) for text in rules.read_file(rules.user_path())]

            if top:
                sources += [("project", rules.team_path(top), text) for text in rules.read_file(rules.team_path(top))]

            found += [dict(kind="rule", profile=None, section=None, text=text, scope=scope,
                           file=str(path) if path else None, disabled=rules.item_hash(text) in disabled)
                      for scope, path, text in sources]
            continue

        profiles = [profile] if profile else sorted({folder.name for root in (data_root(), Path(top) / BASE if top else None)
                                                      if root for folder in (root / "extensions").glob("*") if folder.is_dir()})

        for name in profiles:
            for scope in SCOPES:
                if scope == "project" and not top:
                    continue

                path = file_for(wanted, scope, top, name)
                found += [dict(kind=wanted, profile=name, section=section, text=text, scope=scope, file=str(path),
                               disabled=rules.item_hash(text) in disabled)
                          for section, text in parse_extension(path)]

    return found


def write(path, text, top, scope):
    root = base(scope, top)
    current = root

    for part in path.relative_to(root).parts:
        current = current / part

        if current.is_symlink():
            raise ValueError(f"Refusing to write through a symlink: {current}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    if scope == "project":
        ensure_excluded(Path(top))


def item_text(line, kind):
    match = ITEM.match(line)

    if match:
        return match.group("text")

    return line.strip() if kind == "rule" and line.strip() and not line.lstrip().startswith(("#", "<!--")) else None


def add(kind, text, scope, top=None, profile=None, section=None, must=False):
    text = " ".join(text.split())
    section = " ".join((section or "General").split())

    if not text:
        raise ValueError("Item text is empty")

    path = file_for(kind, scope, top, profile)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    digest = rules.item_hash(text)
    same = [index for index, line in enumerate(lines)
            if item_text(line, kind) is not None and rules.item_hash(item_text(line, kind)) == digest]

    if same:
        current = item_text(lines[same[0]], kind)

        if kind == "rule" and must and not current.upper().startswith("MUST:"):
            lines[same[0]] = f"- MUST: {text}"
            write(path, "\n".join(lines) + "\n", top, scope)
            return path, "upgraded"

        return path, False

    if kind == "rule":
        lines.append(f"- {'MUST: ' if must else ''}{text}")
    else:
        heading = f"## {section}"
        entry = f"- [ ] {text}"

        if heading not in lines:
            lines += ([""] if lines else []) + [heading, entry]
        else:
            index = lines.index(heading) + 1

            while index < len(lines) and not lines[index].startswith("## "):
                index += 1

            while index > 0 and not lines[index - 1].strip():
                index -= 1

            lines.insert(index, entry)

    write(path, "\n".join(lines) + "\n", top, scope)
    return path, True


def read_hashes(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        hashes = data.get("hashes", []) if isinstance(data, dict) else []
        return {item for item in hashes if isinstance(item, str)} if isinstance(hashes, list) else set()
    except (OSError, ValueError):
        return set()


def set_disabled(text, scope, top, disabled):
    known = {rules.item_hash(item["text"]) for item in load(top)}
    digest = rules.item_hash(text)

    if digest not in known:
        raise ValueError(f"No active or disabled item matches: {text}")

    if scope == "project" and not top:
        raise ValueError("Project scope needs a Git work tree; pass --project")

    path = rules.disabled_path(top if scope == "project" else None)
    hashes = read_hashes(path)
    hashes = hashes | {digest} if disabled else hashes - {digest}
    write_json(path, dict(hashes=sorted(hashes)), Path(top) if scope == "project" else data_root())

    if scope == "project":
        ensure_excluded(Path(top))

    note = None

    if not disabled and scope == "project" and digest in read_hashes(rules.disabled_path()):
        note = "Still disabled globally; enable it with --scope global to use it here"

    return path, note


def remove(kind, text, scope, top=None, profile=None):
    path = file_for(kind, scope, top, profile)

    if not path.is_file():
        raise ValueError(f"No file: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    candidates = [(index, item_text(line, kind)) for index, line in enumerate(lines) if item_text(line, kind) is not None]
    matches = [index for index, item in candidates if rules.item_hash(item) == rules.item_hash(text)]
    matches = matches or [index for index, item in candidates if text.lower() in item.lower()]

    if len(matches) != 1:
        raise ValueError(f"{len(matches)} items match {text!r}; give a text that matches exactly one")

    del lines[matches[0]]
    write(path, "\n".join(lines) + "\n", top, scope)
    return path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="List, add, disable, enable or remove Ready Check rules and checklist extensions.")
    parser.add_argument("operation", choices=("list", "add", "disable", "enable", "remove"))
    parser.add_argument("text", nargs="?")
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--profile")
    parser.add_argument("--section")
    parser.add_argument("--scope", choices=SCOPES)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--must", action="store_true")
    args = parser.parse_args()
    result = dict(schema_version=1, action="customize", status="FAIL")

    try:
        top = toplevel(args.project) if args.project else None

        if args.project and not top:
            raise ValueError("--project must be inside a Git work tree")

        if args.operation != "list":
            if not args.text:
                raise ValueError(f"customize {args.operation} needs the item text")

            if not args.scope:
                raise ValueError("Choose --scope project or --scope global")

        if args.operation in {"add", "remove"} and not args.kind:
            raise ValueError("Choose --kind rule, review or qa")

        if args.operation == "add":
            path, added = add(args.kind, args.text, args.scope, top, args.profile, args.section, args.must)
            result.update(file=str(path), added=added)
        elif args.operation == "remove":
            result["file"] = str(remove(args.kind, args.text, args.scope, top, args.profile))
        elif args.operation in {"disable", "enable"}:
            path, note = set_disabled(args.text, args.scope, top, args.operation == "disable")
            result["file"] = str(path)

            if note:
                result["note"] = note

        result.update(status="PASS", items=load(top, args.kind, args.profile))
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
