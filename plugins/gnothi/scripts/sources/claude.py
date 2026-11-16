from __future__ import annotations

import os
from pathlib import Path, PurePath

from sessions import clean_request

CLIENT = "claude"
INTERRUPTED = "[Request interrupted by user"


def root():
    return Path(os.environ.get("GNOTHI_CLAUDE_DIR") or Path.home() / ".claude/projects").expanduser()


def files(base):
    return sorted(Path(base).glob("*/*.jsonl")) if Path(base).is_dir() else []


def tokens(usage):
    from sources import number, obj

    return sum(number(obj(usage).get(key)) for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens"))


def read(path):
    from sources import Builder, obj, parse_ts, records, text_of

    builder, project, counted = Builder(), "", set()

    for record in records(path, builder):
        kind, message = record.get("type"), obj(record.get("message"))
        moment = parse_ts(record.get("timestamp"))
        cwd = record.get("cwd")
        project = project or (PurePath(cwd).name if isinstance(cwd, str) and cwd else "")

        if record.get("isCompactSummary"):
            builder.compactions += 1
            continue

        if kind == "user" and not record.get("isMeta") and not record.get("isSidechain"):
            text = text_of(message.get("content"))

            if text.strip().startswith(INTERRUPTED):
                builder.outcome("interrupted")
                continue

            request = clean_request(text)

            if request:
                builder.start(moment, request)

            continue

        if kind != "assistant":
            continue

        builder.seen(moment)

        if record.get("isSidechain"):
            if builder.current and not any(action.kind == "subagent" for action in builder.current.actions):
                builder.act("Agent")

            continue

        if message.get("id") not in counted:
            builder.tokens(tokens(message.get("usage")))

        if message.get("id"):
            counted.add(message["id"])

        content = message.get("content")

        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue

            if block.get("type") == "tool_use":
                builder.act(str(block.get("name", "")), block.get("input"))
            elif block.get("type") == "text":
                builder.outcome("completed", force=False)

    return builder.build(CLIENT, path, project or Path(path).parent.name)
