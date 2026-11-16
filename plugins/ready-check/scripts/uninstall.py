#!/usr/bin/env python3
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import git_exclude
import settings
from dependency_support import data_root
from managed_storage import MARKER, ROOT_STATE
from profile_runtime import profile_runner
from project import BASE, toplevel

REPORTS = {"reports", "tasks", "feedback.jsonl", "reflect"}
CUSTOM = {"rules.md", "extensions", "disabled.json"}
ENTRY = b"/" + BASE.as_posix().encode() + b"/"
NOTE = "Remove the plugin itself with your client's plugin controls."


def keep(name, reports, custom):
    return name in REPORTS and not reports or name in CUSTOM and not custom


def project_items(top, reports, custom):
    base = top / BASE
    items = []

    if base.is_symlink():
        return [dict(path=str(base), kind="project", action="remove")]

    if not base.is_dir():
        return items

    for child in sorted(base.iterdir()):
        item = dict(path=str(child), kind="project", action="keep" if keep(child.name, reports, custom) else "remove")

        if item["action"] == "remove" and child.name in CUSTOM and git_exclude.git(top, "ls-files", "--", str(child)):
            item.update(action="keep", reason="tracked in Git (shared with the team); remove it with git rm")

        items.append(item)

    if all(item["action"] == "remove" for item in items):
        items.append(dict(path=str(base), kind="project", action="remove"))
        items.append(dict(path=str(top), kind="git-exclude", action="remove"))

    return items


def runner_item(top):
    stored = settings.read(settings.project_path(top))
    profile, application = stored.get("profile"), top / stored.get("application", ".")

    if stored.get("runner") in {None, "local"} or not profile:
        return None

    try:
        runner = profile_runner(application, profile)[0]
        from core_toolchain import runner_data_root

        if not runner.available():
            return dict(path=f"{runner.name}:(not running)", kind="runner-data", action="keep")

        root = runner_data_root(runner)

        if runner.exists(root + "/" + MARKER):
            return dict(path=f"{runner.name}:{root}", kind="runner-data", action="remove", runner=runner)
    except (ImportError, OSError, ValueError):
        return None

    return None


def data_items(custom):
    root = data_root()

    if root.is_symlink() or not root.is_dir():
        return []

    owned = (root / MARKER).is_file()

    if owned and custom:
        return [dict(path=str(root), kind="data", action="remove")]

    names = [child.name for child in root.iterdir()] if owned else [name for name in ROOT_STATE if (root / name).exists()]
    return [dict(path=str(root / name), kind="data", action="keep" if name in CUSTOM and not custom else "remove")
            for name in sorted(names)]


def plan(project, reports, data, custom=False):
    top = toplevel(project)
    items = project_items(top, reports, custom) if top else []

    if data:
        extra = runner_item(top) if top else None
        items += ([extra] if extra else []) + data_items(custom)

    return items


def remove_exclude(top):
    exclusion = git_exclude.plan(top, [])

    if exclusion is None or exclusion["original"] is None:
        return

    lines = exclusion["original"].splitlines(keepends=True)
    kept = [line for line in lines if line.strip() != ENTRY]
    begin = [index for index, line in enumerate(kept) if line.strip() == git_exclude.BEGIN]

    if begin and begin[0] + 1 < len(kept) and kept[begin[0] + 1].strip() == git_exclude.END:
        del kept[begin[0]:begin[0] + 2]

    exclusion["updated"] = b"".join(kept)
    exclusion["action"] = "unchanged" if exclusion["updated"] == exclusion["original"] else "update"
    git_exclude.apply(exclusion)


def remove_path(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def apply(items):
    for item in items:
        if item["action"] != "remove":
            continue

        try:
            remove(item)
            item["status"] = "removed"
        except (OSError, ValueError) as error:
            item.update(status="failed", reason=str(error))
            raise


def remove(item):
    if item["kind"] == "git-exclude":
        remove_exclude(Path(item["path"]))
        return

    if item["kind"] == "runner-data":
        code, _, error = item["runner"].exec(["rm", "-rf", item["path"].split(":", 1)[1]], timeout=120)

        if code:
            raise ValueError(f"Cannot remove runner data: {error.decode(errors='replace')}")
        return

    remove_path(Path(item["path"]))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Remove what Ready Check created; reports, task records, tools and your customizations only on request.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--reports", action="store_true")
    parser.add_argument("--data", action="store_true")
    parser.add_argument("--custom", action="store_true", help="Also remove your rules, checklist extensions and disabled lists")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = dict(schema_version=1, action="uninstall", status="FAIL", note=NOTE)

    items = []

    try:
        items = plan(args.project, args.reports, args.data, args.custom)

        if not args.dry_run:
            apply(items)

        result["status"] = "PLANNED" if args.dry_run else "PASS"
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    result["items"] = [{key: value for key, value in item.items() if key != "runner"} for item in items]

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PASS", "PLANNED"} else 2


if __name__ == "__main__":
    sys.exit(main())
