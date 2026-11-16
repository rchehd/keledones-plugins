#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
from dependency_support import PLUGIN
from git_exclude import apply as apply_exclude, describe as describe_exclude, git, plan as plan_exclude
from project import BASE, toplevel


def branch_name(project):
    name = git(project, "rev-parse", "--abbrev-ref", "HEAD") or git(project, "symbolic-ref", "--short", "HEAD") or ""
    if name == "HEAD":
        return "detached-" + (git(project, "rev-parse", "--short", "HEAD") or "")
    return name


def slug(branch):
    value = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9._-]", "-", branch)).strip("-.")
    digest = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:12]
    return (value[:80] or "no-branch") + "-" + digest


CYRILLIC = dict(zip("абвгґдеєжзиіїйклмнопрстуфхцчшщьюяыэёъ",
                    ["a", "b", "v", "h", "g", "d", "e", "ie", "zh", "z", "y", "i", "i", "i", "k", "l", "m", "n", "o", "p",
                     "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "iu", "ia", "y", "e", "io", ""]))


def title_slug(title):
    title = "".join(CYRILLIC.get(character, character) for character in title.lower())
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    value = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", ascii_title.lower())).strip("-")[:60].strip("-")
    return value or "task-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]


def task_id(title, day=None):
    return f"{title_slug(title)}-{(day or date.today()).isoformat()}"


TASK = re.compile(r".+-\d{4}-\d{2}-\d{2}\Z")


def task_folders(branch_dir):
    if not branch_dir.is_dir():
        return []

    folders = [child for child in branch_dir.iterdir()
               if child.is_dir() and not child.is_symlink() and TASK.match(child.name)]
    return sorted(folders, key=lambda folder: (folder / "report.md").stat().st_mtime
                  if (folder / "report.md").is_file() else folder.stat().st_mtime)


def safe_name(task):
    if task in {".", ".."} or Path(task).name != task or "\\" in task or "/" in task:
        raise ValueError(f"Invalid task name: {task!r}")

    return task


def resolve_task(branch_dir, task):
    folders = task_folders(branch_dir)

    if task:
        task = task.strip()

        if task == branch_dir.name and (branch_dir / "report.md").is_file():
            return None

        if TASK.match(task):
            return safe_name(task)

        pattern = re.compile(re.escape(title_slug(task)) + r"-\d{4}-\d{2}-\d{2}")
        matching = [folder for folder in folders if pattern.fullmatch(folder.name)]
        return matching[-1].name if matching else task_id(task)

    if folders:
        return folders[-1].name

    if (branch_dir / "report.md").is_file():
        return None

    raise ValueError("No Ready Check task on this branch yet; pass --task with the task title")


def all_tasks(top):
    root = Path(top) / BASE / "reports"
    found = []

    if root.is_symlink() or not root.is_dir():
        return found

    for branch_dir in root.iterdir():
        if branch_dir.is_symlink() or not branch_dir.is_dir():
            continue

        folders = task_folders(branch_dir)

        if not folders and (branch_dir / "report.md").is_file():
            folders = [branch_dir]

        for folder in folders:
            report = folder / "report.md"
            found.append(dict(task_id=folder.name, directory=folder, branch_dir=branch_dir.name,
                              mtime=(report if report.is_file() else folder).stat().st_mtime))

    return sorted(found, key=lambda item: item["mtime"], reverse=True)


def checked_directory(project, *names):
    current = project
    for part in (*BASE.parts, "reports", *names):
        current = current / part
        if current.is_symlink() or current.exists() and not current.is_dir():
            raise ValueError(f"Report path must consist of real directories, not symlinks or files: {current}")
    return current


def prepare(project, task=None, dry_run=False):
    project = project.resolve(strict=True)
    if not project.is_dir() or project.is_relative_to(PLUGIN):
        raise ValueError("Reports require an application directory outside the plugin package")
    top = toplevel(project) or project
    branch = branch_name(project)
    branch_dir = checked_directory(top, slug(branch))
    current = resolve_task(branch_dir, task)
    # A legacy branch-level report has no task folder; it counts as one task named after the branch.
    directory = checked_directory(top, slug(branch), current) if current else branch_dir

    if not directory.resolve().is_relative_to(branch_dir.resolve()):
        raise ValueError(f"Task folder escapes the report folder: {directory}")
    exclusion = plan_exclude(top, [BASE.as_posix() + "/"])
    if not dry_run:
        apply_exclude(exclusion)
        directory.mkdir(parents=True, exist_ok=True)
    return dict(branch=branch or "no-branch", task_id=current or slug(branch), directory=str(directory) + "/",
                report=str(directory / "report.md"), summary=str(directory / "summary.json"),
                git_exclude=describe_exclude(exclusion, "PLANNED" if dry_run else "PASS"))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Resolve and prepare the Ready Check report directory for a task on the current branch.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--task", help="Task title or task_id; omit to continue the newest task on the branch")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = dict(schema_version=1, action="reports", status="INCOMPLETE")
    try:
        result.update(prepare(args.project, args.task, args.dry_run))
        result["status"] = "PLANNED" if args.dry_run else "PASS"
    except (OSError, ValueError) as error:
        result["reason"] = str(error)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PASS", "PLANNED"} else 2


if __name__ == "__main__":
    sys.exit(main())
