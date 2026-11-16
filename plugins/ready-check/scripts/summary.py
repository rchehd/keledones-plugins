#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
from fingerprint import work_fingerprint
from git_exclude import git
from project import toplevel, write_json
from reports import prepare

STATUSES = {"PASS", "FAIL", "INCOMPLETE", "N/A", "NOT_SELECTED", "NOT_RUN"}
VERDICTS = ("READY TO PUSH", "PARTIAL CHECK COMPLETE", "BLOCKED", "INCOMPLETE")


def read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def parse_items(values, keys):
    items = []

    for value in values or []:
        parts = value.split(":", len(keys) - 1)
        items.append(dict(zip(keys, parts + [""] * (len(keys) - len(parts)))))

    return items


def append(directory, entry, top):
    path = Path(directory) / "summary.json"
    data = read(path)
    data.setdefault("task_id", entry.pop("task_id"))
    rounds = [item for item in data.get("rounds", []) if isinstance(item, dict) and isinstance(item.get("round"), int)
              and item["round"] != entry["round"]]
    data["rounds"] = sorted(rounds + [entry], key=lambda item: item["round"])
    write_json(path, data, top)
    return path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Record one Ready Check round of a task in its summary.json.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--task", required=True, help="task_id or task title")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--verdict", required=True, choices=VERDICTS)
    parser.add_argument("--static", default="NOT_RUN")
    parser.add_argument("--review", default="NOT_RUN")
    parser.add_argument("--qa", default="NOT_RUN")
    parser.add_argument("--finding", action="append", help="ID:label:stage:area:rc:status")
    parser.add_argument("--qa-case", action="append", help="ID:status:attempt")
    args = parser.parse_args()
    result = dict(schema_version=1, action="summary", status="FAIL")

    try:
        top = toplevel(args.project)

        if not top:
            raise ValueError("summary needs a Git work tree")

        for name in ("static", "review", "qa"):
            if getattr(args, name) not in STATUSES:
                raise ValueError(f"--{name} must be one of {sorted(STATUSES)}")

        target = prepare(args.project, args.task, dry_run=True)

        if not Path(target["directory"]).is_dir():
            raise ValueError(f"No report folder for task {args.task!r}; create it with the reports command first")

        entry = dict(task_id=target["task_id"], round=args.round, ts=datetime.now().isoformat(timespec="seconds"),
                     head=git(top, "rev-parse", "HEAD"), fingerprint=work_fingerprint(top), verdict=args.verdict,
                     stages=dict(static=args.static, review=args.review, qa=args.qa),
                     findings=parse_items(args.finding, ("id", "label", "stage", "area", "rc", "status")),
                     qa=parse_items(args.qa_case, ("id", "status", "attempt")))
        result.update(status="PASS", file=str(append(target["directory"], entry, top)), task_id=target["task_id"])
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
