#!/usr/bin/env python3
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
from fingerprint import work_fingerprint
from git_exclude import git
from project import migrate, migration_lock, toplevel, write_json
from reports import prepare, require_migrated

STATUSES = {"PASS", "FAIL", "INCOMPLETE", "N/A", "NOT_SELECTED", "NOT_RUN"}
VERDICTS = ("READY TO PUSH", "PARTIAL CHECK COMPLETE", "BLOCKED", "INCOMPLETE")
COUNTED_DISPOSITIONS = ("false-positive", "accept-risk")
DISPOSITIONS = (*COUNTED_DISPOSITIONS, "out-of-scope", "fix")


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


def parse_dispositions(values):
    items = {}
    for row in parse_items(values, ("id", "action", "source", "reason")):
        identifier, action = row["id"], row["action"]
        if (not re.fullmatch(r"(?:F|QA)-\d{3,}", identifier) or action not in DISPOSITIONS
                or not row["source"].strip() or not row["reason"].strip() or len(row["reason"]) > 4000):
            raise ValueError(f"A disposition needs ID:action:source:reason, with an action from {', '.join(DISPOSITIONS)}")
        items[identifier] = row
    return list(items.values())


def allowed_verdicts(stages, findings):
    states = set(stages.values())
    blocking = any(item["label"].startswith("issue (blocking)") and item["status"] == "open" for item in findings)

    if "FAIL" in states or blocking:
        return {"BLOCKED"}

    if states & {"INCOMPLETE", "NOT_RUN"} or states == {"NOT_SELECTED"}:
        return {"INCOMPLETE"}

    # A stage can pass with scope left out of it (for example QA kinds excluded from the plan), which is partial too.
    return {"PARTIAL CHECK COMPLETE", "INCOMPLETE"} | (set() if "NOT_SELECTED" in states else {"READY TO PUSH"})


def disposition_key(row):
    return row.get("round"), row.get("id")


def saved_dispositions(data):
    rows = data.get("dispositions")
    if not isinstance(rows, list):
        return {}
    return {disposition_key(row): row for row in rows if isinstance(row, dict) and type(row.get("round")) is int
            and isinstance(row.get("id"), str) and row.get("action") in DISPOSITIONS}


def save(directory, top, task_id, round_number, entry, dispositions):
    path = directory / "summary.json"
    with migration_lock(path.parent):
        data = read(path)
        data.setdefault("task_id", task_id)
        if entry is not None:
            rounds = [row for row in data.get("rounds", []) if isinstance(row, dict)
                      and isinstance(row.get("round"), int) and row["round"] != round_number]
            data["rounds"] = sorted(rounds + [entry], key=lambda row: row["round"])
        if dispositions:
            saved = saved_dispositions(data)
            for row in dispositions:
                decision = dict(row, round=round_number)
                saved[disposition_key(decision)] = decision
            data["dispositions"] = list(saved.values())
        write_json(path, data, top)
    return path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Record a Ready Check round or user decision in the task's summary.json.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--task", required=True, help="task_id or task title")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--verdict", choices=VERDICTS)
    parser.add_argument("--static", default="NOT_RUN")
    parser.add_argument("--static-attempt", choices=("INCOMPLETE",), help="Prior static result before narrowing the current scope")
    parser.add_argument("--review", default="NOT_RUN")
    parser.add_argument("--qa", default="NOT_RUN")
    parser.add_argument("--finding", action="append", help="ID:label:stage:area:rc:status")
    parser.add_argument("--qa-case", action="append", help="ID:status:attempt")
    parser.add_argument("--disposition", action="append", help="ID:action:source:reason for a confirmed user decision")
    args = parser.parse_args()
    result = dict(schema_version=1, action="summary", status="FAIL")

    try:
        top = toplevel(args.project)

        if not top:
            raise ValueError("summary needs a Git work tree")
        if args.round < 1:
            raise ValueError("--round must be positive")

        dispositions = parse_dispositions(args.disposition)
        if args.verdict is None and not dispositions:
            raise ValueError("Provide --verdict for a round or --disposition for a user decision")

        for name in ("static", "review", "qa"):
            if getattr(args, name) not in STATUSES:
                raise ValueError(f"--{name} must be one of {sorted(STATUSES)}")

        stages = dict(static=args.static, review=args.review, qa=args.qa)
        if args.verdict is None and (set(stages.values()) != {"NOT_RUN"} or args.finding or args.qa_case
                                     or args.static_attempt):
            raise ValueError("Provide --verdict when recording stage results, findings or QA cases")
        if args.static_attempt and (args.static != "NOT_SELECTED" or args.review == args.qa == "NOT_SELECTED"):
            raise ValueError("--static-attempt requires statics outside the current scope and review or QA selected")

        findings = parse_items(args.finding, ("id", "label", "stage", "area", "rc", "status"))

        if any(item["status"] not in {"open", "fixed"} for item in findings):
            raise ValueError("A --finding status must be open or fixed")
        allowed = allowed_verdicts(stages, findings)

        if args.verdict is not None and args.verdict not in allowed:
            raise ValueError(f"Verdict {args.verdict!r} contradicts the stages {stages} and open blocking findings; "
                             f"expected {' or '.join(sorted(allowed))}")

        migrate(top)
        target = prepare(args.project, args.task, dry_run=True)
        directory = Path(target["directory"])
        require_migrated(top, directory)

        if not directory.is_dir():
            raise ValueError(f"No report folder for task {args.task!r}; create it with the reports command first")

        entry = None
        if args.verdict is not None:
            entry = dict(round=args.round, ts=datetime.now().isoformat(timespec="seconds"),
                         head=git(top, "rev-parse", "HEAD"), fingerprint=work_fingerprint(top), verdict=args.verdict,
                         stages=stages, findings=findings, qa=parse_items(args.qa_case, ("id", "status", "attempt")))
            if args.static_attempt:
                entry["static_attempt"] = args.static_attempt
        path = save(directory, top, target["task_id"], args.round, entry, dispositions)
        result.update(status="PASS", file=str(path), task_id=target["task_id"])
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
