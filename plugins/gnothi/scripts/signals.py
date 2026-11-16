from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

CORRECTION = re.compile(r"\b(no,? i meant|not that|that's wrong|wrong file|i said|ні,? я мав на увазі|не те|я ж казав|"
                        r"нет,? я имел в виду|не то)\b", re.I)
QUESTION = re.compile(r"\b(why|how does|how do|what is)\b|чому|як працює|почему|как работает", re.I)
DEBUG = re.compile(r"\b(error|bug|fails?|traceback|exception|logs?|fix)\b|помилк|ошибк|баг", re.I)
PLAN = re.compile(r"\bplan\b|план|brainstorm", re.I)
AXES = ("clarity", "focus", "completion", "tool_range")
ARCHETYPES = ("architect", "sprinter", "perfectionist", "explorer", "delegator", "detective")


def similar(first, second, size=300):
    first, second = first[:size], second[:size]

    if 2 * min(len(first), len(second)) < 0.8 * (len(first) + len(second)):
        return False

    matcher = SequenceMatcher(None, first, second, autojunk=False)
    return matcher.quick_ratio() >= 0.8 and matcher.ratio() >= 0.8


def flags(turn, previous):
    request, found = turn.request[:2000], []

    if CORRECTION.search(request):
        found.append("correction")

    if len(request) >= 20 and any(similar(request, earlier) for earlier in previous[-3:]):
        found.append("repeat")

    if QUESTION.search(request):
        found.append("question")

    if DEBUG.search(request):
        found.append("debug")

    if PLAN.search(request) or any(action.kind == "plan" for action in turn.actions):
        found.append("plan")

    return found


def active_minutes(session, cap=30):
    moments = [turn.ts for turn in session.turns if turn.ts] + ([session.ended] if session.ended else [])
    gaps = ((later - earlier).total_seconds() / 60 for earlier, later in zip(moments, moments[1:]))
    return round(sum(min(cap, max(0, gap)) for gap in gaps))


def local(moment):
    return moment.astimezone() if moment else None


def summarize(sessions):
    summary = dict(sessions=len(sessions), turns=0, requests=0, corrections=0, repeats=0, interrupted=0,
                   completed_sessions=0, abandoned=0, verifications=0, plan_first=0, questions=0, debug=0,
                   short_requests=0, big_requests=0, active_days=0, project_switches=0, read_actions=0, actions=0,
                   edit_sessions=0, checks_after_edit_sessions=0, subagent_turns=0, compactions=0, minutes=0,
                   by_weekday=[0] * 7, by_hour=[0] * 24)
    skills, mcp, kinds, projects = Counter(), Counter(), Counter(), {}
    tokens = {"claude": None, "codex": None, "cursor": None}
    names = {"correction": "corrections", "repeat": "repeats", "question": "questions", "debug": "debug"}
    days = {}

    for session in sorted(sessions, key=lambda item: item.started):
        previous = []
        edited = checked_after_edit = False
        project = projects.setdefault(session.project, {"sessions": 0, "turns": 0})
        project["sessions"] += 1
        project["turns"] += len(session.turns)
        summary["compactions"] += session.compactions
        day = local(session.started).date()
        days.setdefault(day, []).append(session.project)

        summary["minutes"] += active_minutes(session)

        if session.turns and session.turns[-1].outcome == "completed":
            summary["completed_sessions"] += 1

        if session.turns and session.turns[-1].outcome in ("interrupted", "error"):
            summary["abandoned"] += 1

        for index, turn in enumerate(session.turns):
            found = flags(turn, previous)
            previous.append(turn.request)
            summary["turns"] += 1
            summary["requests"] += 1
            summary["short_requests"] += len(turn.request) < 80
            summary["big_requests"] += len(turn.request) >= 600
            summary["interrupted"] += turn.outcome == "interrupted"
            summary["plan_first"] += index == 0 and "plan" in found

            for flag in found:
                if flag in names:
                    summary[names[flag]] += 1

            moment = local(turn.ts)

            if moment:
                summary["by_weekday"][moment.weekday()] += 1
                summary["by_hour"][moment.hour] += 1

            if turn.tokens is not None and session.client in tokens:
                tokens[session.client] = (tokens[session.client] or 0) + turn.tokens

            summary["subagent_turns"] += any(action.kind == "subagent" for action in turn.actions)

            for action in turn.actions:
                summary["actions"] += 1
                kinds[action.kind] += 1
                summary["verifications"] += action.kind == "test"
                summary["read_actions"] += action.kind == "read"

                if action.kind == "edit":
                    edited = True
                    checked_after_edit = False
                elif action.kind == "test":
                    checked_after_edit = edited

                if action.kind == "skill" and action.name:
                    skills[action.name] += 1
                elif action.kind == "mcp" and action.name:
                    mcp[action.name] += 1

        summary["edit_sessions"] += edited
        summary["checks_after_edit_sessions"] += checked_after_edit

    summary["active_days"] = len(days)
    summary["project_switches"] = sum(sum(a != b for a, b in zip(order, order[1:])) for order in days.values())
    summary.update(skills=dict(skills), mcp=dict(mcp), kinds=dict(kinds), tokens=tokens, projects=projects)
    return summary


def clamp(value):
    return min(1.0, max(0.0, value))


def score(value):
    return round(clamp(value) * 10, 1)


def axes(summary):
    if not summary["sessions"]:
        return dict.fromkeys(AXES, 0.0)

    r, t, s = max(1, summary["requests"]), max(1, summary["turns"]), max(1, summary["sessions"])
    tools = len(summary["skills"]) + len(summary["mcp"]) + (1 if summary["subagent_turns"] else 0)
    switches = summary["project_switches"] / max(1, summary["active_days"])
    return dict(
        clarity=score(1 - clamp((summary["corrections"] + summary["repeats"]) / r * 4)),
        focus=score(1 - clamp(switches / 6 * 0.7 + summary["abandoned"] / s * 0.3)),
        completion=score(summary["completed_sessions"] / s * (1 - summary["interrupted"] / t)),
        tool_range=score(tools / 10),
    )


def archetypes(summary):
    if not summary["sessions"]:
        return dict.fromkeys(ARCHETYPES, 0.0)

    r, t, s = max(1, summary["requests"]), max(1, summary["turns"]), max(1, summary["sessions"])
    clarity = axes(summary)["clarity"] / 10
    pace = clamp(summary["turns"] / s / 20)
    return dict(
        architect=score(0.7 * clamp(summary["plan_first"] / s * 2) + 0.3 * clarity),
        sprinter=score(0.6 * clamp(summary["short_requests"] / r * 1.2) + 0.4 * pace),
        perfectionist=score(0.5 * clamp(summary["corrections"] / r * 4) + 0.5 * clamp(summary["verifications"] / t * 2)),
        explorer=score(0.6 * clamp(summary["questions"] / r * 4) +
                       0.4 * clamp(summary["read_actions"] / max(1, summary["actions"]) * 1.5)),
        delegator=score(0.5 * clamp(summary["big_requests"] / r * 4) + 0.3 * clamp(summary["subagent_turns"] / t * 5) +
                        0.2 * (1 - pace)),
        detective=score(summary["debug"] / r * 2.5),
    )
