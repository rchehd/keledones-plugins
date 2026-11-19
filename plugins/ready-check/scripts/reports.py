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
from git_exclude import describe as describe_exclude, git, plan as plan_exclude
from project import (BASE, LEGACY_BASE, TASK_REPORT, branch_report_directory, ensure_excluded,
                     migrate, migration_lock, redirected, toplevel)


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


def branch_tasks(branch_dir):
    if redirected(branch_dir) or not branch_dir.is_dir():
        return {}
    found = {child.name: child for child in branch_dir.iterdir()
             if TASK_REPORT.fullmatch(child.name) and not redirected(child) and child.is_dir()}
    branch_report = branch_report_directory(branch_dir)
    if branch_report:
        found[branch_dir.name] = branch_report
    return found


def report_mtime(folder):
    report = folder / "report.md"
    return (report if not redirected(report) and report.is_file() else folder).stat().st_mtime


def safe_name(task):
    if task in {".", ".."} or Path(task).name != task or "\\" in task or "/" in task:
        raise ValueError(f"Invalid task name: {task!r}")

    return task


def resolve_task(branch_dir, folders, task):
    if task:
        task = task.strip()

        if task in folders or TASK_REPORT.fullmatch(task):
            return safe_name(task)

        pattern = re.compile(re.escape(title_slug(task)) + r"-\d{4}-\d{2}-\d{2}")
        matching = [name for name in folders if pattern.fullmatch(name)]
        return max(matching, key=lambda name: report_mtime(folders[name])) if matching else task_id(task)

    dated = [name for name in folders if name != branch_dir.name]
    if dated:
        return max(dated, key=lambda name: report_mtime(folders[name]))

    if branch_dir.name in folders:
        return branch_dir.name

    raise ValueError("No Ready Check task on this branch yet; pass --task with the task title")


def tasks_in(root):
    found = []

    if redirected(root) or not root.is_dir():
        return found

    for branch_dir in root.iterdir():
        for name, folder in branch_tasks(branch_dir).items():
            found.append(dict(task_id=name, directory=folder, branch_dir=branch_dir.name, mtime=report_mtime(folder)))

    return found


def all_tasks(top):
    found = {}
    for base in (LEGACY_BASE, BASE):
        for item in tasks_in(Path(top) / base / "reports"):
            found[item["branch_dir"], item["task_id"]] = item
    return sorted(found.values(), key=lambda item: item["mtime"], reverse=True)


def checked_directory(project, *names):
    current = project
    for part in (*BASE.parts, "reports", *names):
        current = current / part
        if redirected(current) or current.exists() and not current.is_dir():
            raise ValueError(f"Report path must consist of real directories, not symlinks or files: {current}")
    return current


def locate(top, branch, task, dry_run):
    branch_id = slug(branch)
    branch_dir = checked_directory(top, branch_id)
    folders = branch_tasks(top / LEGACY_BASE / "reports" / branch_id)
    folders.update(branch_tasks(branch_dir))
    current = resolve_task(branch_dir, folders, task)
    directory = folders.get(current)
    if directory is None:
        directory = checked_directory(top, branch_id, current)
    if dry_run:
        exclusion = plan_exclude(top, [BASE.as_posix() + "/"])
    else:
        require_migrated(top, directory)
        exclusion = ensure_excluded(top)
        directory.mkdir(parents=True, exist_ok=True)
    return dict(branch=branch or "no-branch", task_id=current, directory=str(directory) + "/",
                report=str(directory / "report.md"), summary=str(directory / "summary.json"),
                git_exclude=describe_exclude(exclusion, "PLANNED" if dry_run else "PASS"))


def require_migrated(top, directory):
    if not directory.is_relative_to(top / BASE):
        raise ValueError(f"Report is still in legacy Ready Check storage; migration could not move it: {directory}")


def prepare(project, task=None, dry_run=False):
    project = project.resolve(strict=True)
    if not project.is_dir() or project.is_relative_to(PLUGIN):
        raise ValueError("Reports require an application directory outside the plugin package")
    top = toplevel(project) or project
    branch = branch_name(project)
    if dry_run:
        return locate(top, branch, task, dry_run=True)
    migrate(top)
    with migration_lock(top / BASE):
        return locate(top, branch, task, dry_run=False)


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
