from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

import signals
from redact import excerpt
from sessions import load, window

PRIORITY = ("correction", "repeat", "debug", "question", "plan")


def iso(day):
    return day.isoformat() if day else None


def spread(items):
    def inverse(index):
        value, base = 0.0, 0.5

        while index:
            value += (index & 1) * base
            index >>= 1
            base /= 2

        return value

    return [items[index] for index in sorted(range(len(items)), key=inverse)]


def ordered(sessions):
    groups = defaultdict(list)

    for session in sorted(sessions, key=lambda item: item.started):
        groups[session.project].append(session)

    queues = [spread(group) for _, group in sorted(groups.items())]
    result = []

    while any(queues):
        for queue in queues:
            if queue:
                result.append(queue.pop(0))

    return result


def evidence_item(session):
    previous, flagged, found = [], [], set()

    for index, turn in enumerate(session.turns):
        flags = signals.flags(turn, previous)
        previous.append(turn.request)
        found.update(flags)

        if turn.outcome == "interrupted":
            flags.append("interrupted")
            found.add("interrupted")

        if index and flags:
            rank = min((PRIORITY.index(flag) for flag in flags if flag in PRIORITY), default=len(PRIORITY))
            flagged.append((rank, index, turn.request))

    picks = [request for _, _, request in sorted(flagged)[:2]]
    return {"id": session.id, "client": session.client, "project": session.project,
            "date": session.started.astimezone().date().isoformat(), "turns": len(session.turns),
            "flags": sorted(found), "excerpts": [excerpt(text) for text in [session.turns[0].request, *picks]]}


def block(sessions, archetypes_on):
    summary = signals.summarize(sessions)

    if not sessions:
        return {"summary": summary, "axes": None, "archetypes": None}

    return {"summary": summary, "axes": signals.axes(summary),
            "archetypes": signals.archetypes(summary) if archetypes_on else None}


def anonymize(data, sessions):
    names = {}

    for session in sorted(sessions, key=lambda item: item.started):
        names.setdefault(session.project, f"project-{len(names) + 1}")

    for part in (data["current"], data["previous"]):
        if part:
            part["summary"]["projects"] = {names[name]: value for name, value in part["summary"]["projects"].items()}

    for item in data["projects"]:
        item["name"] = names[item["name"]]

    for item in data["sources"]:
        item.pop("root", None)

    for kind in ("skills", "mcp"):
        counts = data["tools"][kind]
        data["tools"][kind] = {f"{kind.rstrip('s')}-{index}": counts[name] for index, name in enumerate(sorted(counts), 1)}


def build(period, today=None, budget=30000, metrics_only=False, archetypes_on=False):
    today = today or date.today()
    span = window(period, today)
    previous = span["previous"]
    sessions, sources = load(previous["start"] if previous else span["start"], today)

    def day(session):
        return session.started.astimezone().date()

    current = [session for session in sessions if span["start"] is None or day(session) >= span["start"]]
    earlier = [session for session in sessions if previous and day(session) <= previous["end"]]

    for entry in sources:
        entry["sessions"] = sum(session.client == entry["client"] for session in current)

    now = block(current, archetypes_on)
    summary = now["summary"]
    months = defaultdict(list)

    if period == "all":
        for session in current:
            months[day(session).strftime("%Y-%m")].append(session)

    data = {
        "schema_version": 1,
        "period": {"name": period, "start": iso(span["start"]), "end": iso(span["end"]),
                   "previous": {"start": iso(previous["start"]), "end": iso(previous["end"])} if previous else None},
        "sources": sources,
        "metrics_only": metrics_only,
        "current": now,
        "previous": block(earlier, archetypes_on) if previous else None,
        "trend": [{"month": month, "axes": signals.axes(signals.summarize(group))} for month, group in sorted(months.items())],
        "activity": {"by_weekday": summary["by_weekday"], "by_hour": summary["by_hour"]},
        "tools": {"skills": summary["skills"], "mcp": summary["mcp"], "kinds": summary["kinds"],
                  "subagent_turns": summary["subagent_turns"]},
        "friction": {key: summary[key] for key in ("corrections", "repeats", "interrupted", "compactions")},
        "tokens": dict(summary["tokens"], note="Cursor not counted"),
        "projects": [{"name": name, **value} for name, value in
                     sorted(summary["projects"].items(), key=lambda item: -item[1]["sessions"])],
        "evidence": [],
    }

    if metrics_only:
        anonymize(data, sessions)
        return data

    size = len(json.dumps(data, ensure_ascii=False))

    for session in ordered(current):
        item = evidence_item(session)
        cost = len(json.dumps(item, ensure_ascii=False)) + 2

        if (size + cost) / 4 > budget:
            break

        data["evidence"].append(item)
        size += cost

    return data
