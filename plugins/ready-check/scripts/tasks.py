#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
from git_exclude import git
from project import BASE, ensure_excluded, migrate, migration_lock, project_locations, redirected, toplevel
from reports import branch_name, slug

MAX_PROMPT = 20 * 1024
RETENTION_DAYS = 30
COMMAND = re.compile(r"\s*(?:/ready:[a-z-]+|[/$](?:check|review|qa|setup|uninstall))\s*\Z")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}\.jsonl\Z")
# Codex sends answers from its question UI as a prompt wrapped in this tag around a JSON list.
CODEX_REPLY = re.compile(r"<send_user_message_question_reply>\s*(.*?)\s*</send_user_message_question_reply>", re.S)


def text(value):
    return value.strip() if isinstance(value, str) else ""


def codex_answers(match):
    try:
        items = json.loads(match.group(1))
    except ValueError:
        return match.group(0)

    if not isinstance(items, list):
        return match.group(0)

    lines = [f"Q: {text(item.get('question'))}\nA: {text(item.get('answer'))}"
             for item in items if isinstance(item, dict)]
    return "\n".join(lines) or match.group(0)


def normalize(prompt):
    return CODEX_REPLY.sub(codex_answers, prompt).strip()


def truncate(prompt):
    return prompt.encode("utf-8", "replace")[:MAX_PROMPT].decode("utf-8", "ignore")


def directory(top, branch):
    current = top

    for part in (*BASE.parts, "tasks", slug(branch)):
        current = current / part

        if current.resolve() != current or current.exists() and not current.is_dir():
            raise ValueError(f"Task records need real directories: {current}")

    return current


def append(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)

    try:
        if os.name != "nt":
            os.write(descriptor, data)
            return

        # Windows append is seek-then-write; a byte lock serialises concurrent writers.
        import msvcrt
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)

        try:
            os.lseek(descriptor, 0, os.SEEK_END)
            os.write(descriptor, data)
        finally:
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(descriptor)


def repeated(path, session, prompt):
    try:
        with open(path, "rb") as stream:
            stream.seek(max(0, stream.seek(0, os.SEEK_END) - 4 * MAX_PROMPT))
            last = json.loads(stream.read().decode("utf-8", "replace").strip().split("\n")[-1])
    except (OSError, ValueError, IndexError):
        return False

    return isinstance(last, dict) and last.get("session") == session and last.get("prompt") == truncate(prompt)


def record(top, client, session, prompt, now=None):
    if not isinstance(prompt, str):
        return None

    prompt = normalize(prompt)

    if not prompt or COMMAND.match(prompt):
        return None

    top = Path(top)
    migrate(top)
    now = now or datetime.now()
    branch = branch_name(top) or "no-branch"
    line = dict(ts=now.isoformat(timespec="seconds"), client=client, session=session, branch=branch,
                head=git(top, "rev-parse", "HEAD"), prompt=truncate(prompt))
    with migration_lock(top / BASE):
        folder = directory(top, branch)
        if not folder.exists():
            ensure_excluded(top)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{now:%Y-%m-%d}.jsonl"
        if prompt.startswith("Q: ") and repeated(path, session, prompt):
            return path
        append(path, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))

    return path


def read_records(paths, limit):
    found, seen = [], set()
    sources = 0
    for path in paths:
        if redirected(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            continue
        sources += 1
        keys = set()
        for text in reversed(lines):
            try:
                item = json.loads(text)
            except ValueError:
                continue
            if isinstance(item, dict):
                key = json.dumps(item, sort_keys=True)
                if key not in seen:
                    found.append(item)
                    keys.add(key)
                    if len(paths) == 1 and len(found) >= limit:
                        return found[:limit]
        seen.update(keys)
    if sources > 1:
        found.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    return found[:limit]


def recent(top, branch=None, limit=20):
    folder = directory(Path(top), branch or branch_name(Path(top)) or "no-branch")
    locations = project_locations(top, folder.relative_to(Path(top) / BASE))
    daily = {}
    for location in locations:
        if location.is_dir() and not redirected(location):
            for path in location.iterdir():
                if DAY.match(path.name):
                    daily.setdefault(path.name, []).append(path)

    found = []
    for day in sorted(daily, reverse=True):
        found.extend(read_records(daily[day], limit - len(found)))
        if len(found) >= limit:
            break
    return found


def prune(top, days=RETENTION_DAYS, now=None):
    top = Path(top)
    roots = [root for root in project_locations(top, "tasks") if root.is_dir() and not redirected(root)]
    if not roots:
        return 0
    cutoff = ((now or datetime.now()) - timedelta(days=days)).strftime("%Y-%m-%d")
    removed = 0
    tracked = git(top, "ls-files", "-z", "--", *(root.relative_to(top).as_posix() for root in roots))
    if tracked is None:
        return removed
    protected = {top / name for name in tracked.split("\0") if name}

    storage = top / BASE
    with migration_lock(storage):
        ensure_excluded(top)
        for root in roots:
            if redirected(root) or not root.is_dir():
                continue
            for folder in root.iterdir():
                if redirected(folder) or not folder.is_dir():
                    continue
                try:
                    items = list(folder.iterdir())
                except OSError:
                    continue
                for path in items:
                    try:
                        if (DAY.match(path.name) and path.name[:10] < cutoff and path not in protected
                                and path.is_file() and not redirected(path)):
                            path.unlink(missing_ok=True)
                            removed += 1
                    except OSError:
                        continue
                with suppress(OSError):
                    folder.rmdir()

    return removed


def sessions(records):
    grouped = {}

    for item in records:
        key = (item.get("client"), item.get("session"))
        entry = grouped.setdefault(key, dict(session=item.get("session"), client=item.get("client"),
                                             first=item.get("ts"), last=item.get("ts"), prompts=[]))
        entry["first"] = item.get("ts")
        entry["prompts"].insert(0, item.get("prompt"))

    return list(grouped.values())


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Show recent prompts recorded for a branch, newest session first.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--branch")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    result = dict(schema_version=1, action="tasks", status="FAIL")

    try:
        top = toplevel(args.project)
        if not top:
            raise ValueError("Task records need a Git work tree")

        branch = args.branch or branch_name(top) or "no-branch"
        result.update(status="PASS", branch=branch, sessions=sessions(recent(top, branch, max(args.limit, 1))))
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
