from __future__ import annotations

import json
from datetime import datetime, timezone

from redact import redact
from sessions import Session, Turn, classify, session_id

DETAIL_KEYS = ("command", "cmd", "skill", "file_path", "path", "target_file")


def records(path, counter):
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except ValueError:
                counter.skipped += 1
                continue

            if isinstance(record, dict):
                yield record
            else:
                counter.skipped += 1


def obj(value):
    return value if isinstance(value, dict) else {}


def number(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_ts(value):
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def detail(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value

    if isinstance(value, dict):
        return next((str(value[key]) for key in DETAIL_KEYS if value.get(key)), "")

    return ""


def text_of(content):
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "\n".join(str(block.get("text", "")) for block in content
                         if isinstance(block, dict) and block.get("type") in ("text", "input_text", "output_text"))

    return ""


class Builder:
    def __init__(self):
        self.turns, self.times = [], []
        self.skipped = self.compactions = 0

    @property
    def current(self):
        return self.turns[-1] if self.turns else None

    def seen(self, moment):
        if moment:
            self.times.append(moment)

    def start(self, moment, request):
        self.seen(moment)
        self.turns.append(Turn(moment, redact(request)))

    def act(self, tool, value=None):
        if self.current:
            self.current.actions.append(classify(tool, detail(value)))

    def tokens(self, count):
        count = number(count)

        if self.current and count:
            self.current.tokens = (self.current.tokens or 0) + count

    def outcome(self, outcome, force=True):
        if self.current and (force or self.current.outcome == "unknown"):
            self.current.outcome = outcome

    def build(self, client, path, project):
        return Session(client, session_id(client, path), project, str(path), min(self.times, default=None),
                       max(self.times, default=None), self.turns, self.compactions, self.skipped)


from sources import claude, codex, cursor  # noqa: E402

ADAPTERS = (claude, codex, cursor)
