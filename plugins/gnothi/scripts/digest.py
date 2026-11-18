from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from itertools import groupby

import signals
from redact import excerpt
from sessions import CHAT_CLIENTS, load, window
from sources import chat_history

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

    axes = signals.axes(summary)
    agents = [session for session in sessions if session.client not in CHAT_CLIENTS]
    agent_summary = summary if len(agents) == len(sessions) else signals.summarize(agents)
    if agent_summary is not summary:
        agent_axes = signals.axes(agent_summary) if agents else {}
        axes.update({key: agent_axes.get(key) for key in ("focus", "completion", "tool_range")})
        summary["agent_sessions"] = len(agents)
        summary["minutes"] = agent_summary["minutes"]
        summary["project_switches"] = agent_summary["project_switches"]

    return {"summary": summary, "axes": axes,
            "archetypes": signals.archetypes(agent_summary) if archetypes_on and agents else None}


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


def monthly_axes(sessions):
    months = defaultdict(list)
    for session in sessions:
        if session.client in CHAT_CLIENTS:
            for month, turns in groupby(session.turns, key=lambda turn: turn.ts.astimezone().strftime("%Y-%m")):
                months[month].append(chat_history.with_turns(session, list(turns)))
        else:
            months[session.started.astimezone().strftime("%Y-%m")].append(session)
    return [{"month": month, "axes": block(group, False)["axes"]} for month, group in sorted(months.items())]


def build(period, today=None, budget=30000, metrics_only=False, archetypes_on=False,
          chat_exports=(), chat_samples=()):
    today = today or date.today()
    span = window(period, today)
    previous = span["previous"]
    sessions, sources = load(previous["start"] if previous else span["start"], today)

    def day(session):
        return session.started.astimezone().date()

    current = [session for session in sessions if span["start"] is None or day(session) >= span["start"]]
    earlier = [session for session in sessions if previous and day(session) <= previous["end"]]

    chat_sessions, chat_sources = chat_history.import_sources(chat_exports, chat_samples)
    current.extend(chat_history.in_period(chat_sessions, span["start"], span["end"]))
    if previous:
        earlier.extend(chat_history.in_period(chat_sessions, previous["start"], previous["end"]))
    sources.extend(chat_sources)

    for entry in sources:
        entry["sessions"] = sum(session.client == entry["client"] for session in current)

    now = block(current, archetypes_on)
    summary = now["summary"]

    data = {
        "schema_version": 1,
        "period": {"name": period, "start": iso(span["start"]), "end": iso(span["end"]),
                   "previous": {"start": iso(previous["start"]), "end": iso(previous["end"])} if previous else None},
        "sources": sources,
        "metrics_only": metrics_only,
        "current": now,
        "previous": block(earlier, archetypes_on) if previous else None,
        "trend": monthly_axes(current) if period == "all" else [],
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
        anonymize(data, [*current, *earlier])
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
