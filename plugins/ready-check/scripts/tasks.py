#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
from git_exclude import git
from project import BASE, ensure_excluded, toplevel
from reports import branch_name, slug

MAX_PROMPT = 20 * 1024
RETENTION_DAYS = 30
COMMAND = re.compile(r"\s*(?:/ready:[a-z-]+|[/$](?:check|review|qa|setup|uninstall))\s*\Z")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}\.jsonl\Z")
# Codex sends answers from its question UI as a prompt wrapped in this tag around a JSON list.
CODEX_REPLY = re.compile(r"<send_user_message_question_reply>\s*(.*?)\s*</send_user_message_question_reply>", re.S)


def codex_answers(match):
    try:
        items = json.loads(match.group(1))
    except ValueError:
        return match.group(0)

    if not isinstance(items, list):
        return match.group(0)

    lines = [f"Q: {item.get('question', '').strip()}\nA: {str(item.get('answer', '')).strip()}"
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

        if current.is_symlink() or current.exists() and not current.is_dir():
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


def record(top, client, session, prompt, now=None):
    if not isinstance(prompt, str):
        return None

    prompt = normalize(prompt)

    if not prompt or COMMAND.match(prompt):
        return None

    top = Path(top)
    now = now or datetime.now()
    branch = branch_name(top) or "no-branch"
    folder = directory(top, branch)

    if not folder.exists():
        ensure_excluded(top)
        folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"{now:%Y-%m-%d}.jsonl"
    line = dict(ts=now.isoformat(timespec="seconds"), client=client, session=session, branch=branch,
                head=git(top, "rev-parse", "HEAD"), prompt=truncate(prompt))
    append(path, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))

    return path


def recent(top, branch=None, limit=20):
    folder = directory(Path(top), branch or branch_name(Path(top)) or "no-branch")
    found = []

    if not folder.is_dir():
        return found

    for path in sorted((item for item in folder.iterdir() if DAY.match(item.name)), reverse=True):
        for text in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                item = json.loads(text)
            except ValueError:
                continue

            if isinstance(item, dict):
                found.append(item)

            if len(found) >= limit:
                return found

    return found


def prune(top, days=RETENTION_DAYS, now=None):
    root = Path(top) / BASE / "tasks"
    cutoff = ((now or datetime.now()) - timedelta(days=days)).strftime("%Y-%m-%d")
    removed = 0

    if root.is_symlink() or not root.is_dir():
        return removed

    for folder in root.iterdir():
        if folder.is_symlink() or not folder.is_dir():
            continue

        for path in folder.iterdir():
            if DAY.match(path.name) and path.name[:10] < cutoff and path.is_file() and not path.is_symlink():
                path.unlink()
                removed += 1

        if not any(folder.iterdir()):
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
