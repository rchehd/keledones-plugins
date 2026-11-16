#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
from project import BASE, ensure_excluded, toplevel
from reports import all_tasks, branch_name, prepare
from tasks import append


def last_round(directory):
    try:
        data = json.loads((Path(directory) / "summary.json").read_text(encoding="utf-8"))
        rounds = data.get("rounds") or []
        return rounds[-1].get("round") if rounds else None
    except (OSError, ValueError, AttributeError):
        return None


def path(top):
    return Path(top) / BASE / "feedback.jsonl"


def add(top, project, task, returned, by, reason, missed, area, source):
    branch = branch_name(top) or "no-branch"
    known = {item["task_id"]: item for item in all_tasks(top)}

    if task == "unknown":
        directory = None
    elif task in known:
        directory = known[task]["directory"]
        branch = known[task]["branch_dir"]
    else:
        target = prepare(project, task, dry_run=True)
        directory = Path(target["directory"])

        if not directory.is_dir():
            raise LookupError(f"No Ready Check task {task!r} on this branch")

        task = target["task_id"]

    entry = dict(ts=datetime.now().isoformat(timespec="seconds"), task=task, branch=branch,
                 round=last_round(directory) if directory else None, returned=returned, by=by, reason=reason,
                 missed=missed, area=area, source=source)
    ensure_excluded(top)
    path(top).parent.mkdir(parents=True, exist_ok=True)
    append(path(top), (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8"))
    return entry


def recent(top, limit=20):
    try:
        lines = path(top).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    items = []

    for line in reversed(lines):
        try:
            item = json.loads(line)
        except ValueError:
            continue

        if isinstance(item, dict):
            items.append(item)

        if len(items) >= limit:
            break

    return items


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Record or list feedback about tasks returned after Ready Check.")
    parser.add_argument("operation", choices=("add", "list"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--task", help="task_id or title; 'unknown' when it cannot be identified; default: newest task on the branch")
    parser.add_argument("--returned", choices=("yes", "no"))
    parser.add_argument("--by", choices=("lead", "qa", "client", "other"), default="other")
    parser.add_argument("--reason", default="unknown")
    parser.add_argument("--missed", choices=("yes", "no", "unknown"), default="unknown")
    parser.add_argument("--area", default="unknown")
    parser.add_argument("--source", choices=("chat", "manual"), default="manual")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    result = dict(schema_version=1, action="feedback", status="FAIL")
    code = 2

    try:
        top = toplevel(args.project)

        if not top:
            raise ValueError("feedback needs a Git work tree")

        if args.operation == "list":
            result.update(status="PASS", records=recent(top, max(args.limit, 1)))
        else:
            if not args.returned:
                raise ValueError("feedback add needs --returned yes|no")

            try:
                result.update(status="PASS", record=add(top, args.project, args.task, args.returned == "yes", args.by,
                                                        args.reason, args.missed, args.area, args.source))
            except (LookupError, ValueError) as error:
                result.update(status="CHOOSE_TASK", reason=str(error),
                              tasks=[dict(task_id=item["task_id"], branch=item["branch_dir"]) for item in all_tasks(top)[:5]])
                code = 3

        if result["status"] == "PASS":
            code = 0
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
