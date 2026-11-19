from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sessions import clean_request

CLIENT = "cursor"
STAMP = re.compile(r"<timestamp>\s*(\w+, \w+ \d+, \d{4}, \d+:\d+ [AP]M)\s*\(UTC(?:([+-])(\d{1,2})(?::?(\d{2}))?)?\)")


def root():
    return Path(os.environ.get("GNOTHI_CURSOR_DIR") or Path.home() / ".cursor/projects").expanduser()


def files(base):
    return sorted(Path(base).glob("*/agent-transcripts/*/*.jsonl")) if Path(base).is_dir() else []


def project_name(folder):
    return folder.split("Projects-", 1)[1] if "Projects-" in folder else folder


def stamp(text):
    match = STAMP.search(text)

    if not match:
        return None

    try:
        local = datetime.strptime(match.group(1), "%A, %b %d, %Y, %I:%M %p")
    except ValueError:
        return None

    offset = timedelta(hours=int(match.group(3) or 0), minutes=int(match.group(4) or 0))
    zone = timezone(-offset if match.group(2) == "-" else offset)
    return local.replace(tzinfo=zone).astimezone(timezone.utc)


def outcome(status):
    status = str(status or "").lower()

    if status == "success":
        return "completed"

    if any(word in status for word in ("cancel", "abort", "interrupt")):
        return "interrupted"

    return "error" if "error" in status else "unknown"


def read(path):
    from sources import Builder, obj, records, text_of

    builder = Builder()
    fallback = datetime.fromtimestamp(Path(path).stat().st_mtime, timezone.utc)

    for record in records(path, builder):
        role, message = record.get("role"), obj(record.get("message"))

        if record.get("type") == "turn_ended":
            builder.outcome(outcome(record.get("status")))
        elif role in ("user", "tool"):
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    builder.tool_answer(block.get("tool_use_id"), block.get("content"))
            if role == "tool":
                builder.tool_answer(message.get("tool_call_id"), content)
                continue
            text = text_of(content)
            request = clean_request(text)

            if request:
                builder.start(stamp(text) or (builder.current and builder.current.ts) or fallback, request)
        elif role == "assistant":
            content = message.get("content")

            if isinstance(content, str):
                builder.visible("assistant", content)
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    builder.act(str(block.get("name", "")), block.get("input"), block.get("id"))
                elif block.get("type") == "text":
                    builder.visible("assistant", block.get("text"))

    return builder.build(CLIENT, path, project_name(Path(path).parents[2].name))
