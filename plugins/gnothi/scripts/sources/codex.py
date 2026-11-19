from __future__ import annotations

import os
from pathlib import Path, PurePath

from redact import redact
from sessions import clean_request

CLIENT = "codex"
OUTCOMES = {"task_complete": "completed", "turn_aborted": "interrupted"}


def root():
    return Path(os.environ.get("GNOTHI_CODEX_DIR") or Path.home() / ".codex/sessions").expanduser()


def files(base):
    return sorted(Path(base).rglob("*.jsonl")) if Path(base).is_dir() else []


def read(path):
    from sources import Builder, obj, parse_ts, records, text_of

    builder, project = Builder(), ""

    def start(moment, text):
        if builder.menu_reply(text):
            return
        request = clean_request(text)
        current = builder.current

        if not request:
            return

        if current and current.request == redact(request) and current.ts and moment and \
                abs((moment - current.ts).total_seconds()) < 60:
            return

        builder.start(moment, request)

    for record in records(path, builder):
        kind, payload = record.get("type"), obj(record.get("payload"))
        moment = parse_ts(record.get("timestamp"))
        builder.seen(moment)

        if kind == "session_meta" and isinstance(payload.get("cwd"), str) and payload["cwd"]:
            builder.cwd = payload["cwd"]
            project = PurePath(builder.cwd).name
        elif kind == "turn_context" and isinstance(payload.get("cwd"), str) and payload["cwd"]:
            builder.cwd = payload["cwd"]
        elif kind == "compacted" or (kind == "response_item" and payload.get("type") == "compaction"):
            builder.compactions += 1
        elif kind == "response_item":
            payload_type = payload.get("type")
            if payload_type in ("function_call", "custom_tool_call"):
                builder.act(str(payload.get("name", "")), payload.get("arguments") or payload.get("input"),
                            payload.get("call_id"))
            elif payload_type in ("function_call_output", "custom_tool_call_output"):
                builder.tool_answer(payload.get("call_id"), payload.get("output"))
            elif payload_type == "message" and payload.get("role") == "assistant":
                builder.visible("assistant", text_of(payload.get("content")))
        elif kind == "event_msg":
            event = payload.get("type")
            item = obj(payload.get("item"))

            if event == "item_completed" and item.get("type") == "UserMessage":
                start(moment, text_of(item.get("content")))
            elif event == "user_message":
                start(moment, text_of(payload.get("message")))
            elif event == "token_count":
                builder.tokens(obj(obj(payload.get("info")).get("last_token_usage")).get("total_tokens"))
            elif event in OUTCOMES:
                builder.outcome(OUTCOMES[event])

    return builder.build(CLIENT, path, project or Path(path).stem)
