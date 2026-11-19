from __future__ import annotations

import re
from collections import Counter, defaultdict

from redact import excerpt
from sessions import CHAT_CLIENTS, Interaction

CRITERIA = {
    "review": ("review_scope", "review_evidence", "review_permission"),
    "bug_fix": ("fix_expected", "fix_cause", "fix_recheck"),
}
STATUSES = ("observed", "gap", "unknown", "not_applicable")
STEP_ACTORS = {
    "review_request": "user", "fix_request": "user", "scope": "user", "redirect": "user",
    "approve": "user", "findings": "agent", "read": "agent", "cause": "agent", "edit": "agent",
    "check": "agent",
}
REVIEW = re.compile(r"^\s*(?:(?:please|do|давай|знову|зроби|проведи)\s+)*(?:review|code review|рев[’'ь]?ю)\b|"
                    r"\b(?:find blockers|знайди блокер\w*|переглянь (?:код|зміни|diff))\b", re.I)
FIX = re.compile(r"^\s*(?:(?:please|then|тепер|давай)\s+)*(?:fix\b|apply (?:the )?fixes\b|"
                 r"пофікс\w*|фікс\w*|виправ\w*)", re.I)
DEFECT = re.compile(r"\b(?:bug|regression|broken|fail\w*|error|баг\w*|регресі\w*|помил\w*|не працює)\b", re.I)
NEW_TASK = re.compile(r"^\s*(?:new task|unrelated task|next task|нова задача|інша задача|наступна задача)\b", re.I)
REVIEW_LIMIT = re.compile(r"\b(?:review only|findings only|blockers only|only (?:report |the )?blockers|"
                          r"(?:do not|don't) (?:edit|fix|change)|no (?:edits|fixes)|без (?:правок|змін|фіксів)|"
                          r"(?:лише|тільки) (?:рев[’'ь]?ю|блокер\w*|зауваження)|не (?:редагуй|виправляй|змінюй))\b", re.I)
REVIEW_SCOPE = re.compile(r"\b(?:only|scope|focus on|лише|тільки|зосередься|обмежся)\b", re.I)
FIX_QUESTION = re.compile(r"\b(?:fix|edit|apply (?:the )?fixes|виправ\w*|фікс\w*|внести правки)\b", re.I)
EDIT_OFFER = re.compile(
    r"\b(?:(?:should (?:i|we)|shall (?:i|we)|may i|can i|do you want me to|would you like me to)\s+"
    r"(?:(?:go ahead and|also|now|just)\s+)*(?:fix|edit|(?:make|apply) (?:the |that |these |those )?(?:fix(?:es)?|edits?|changes?))\b"
    r"|(?:чи\s+(?:(?:мені|можна|варто|можу(?:\s+я)?)\s+)?|хочеш,?\s+щоб\s+я\s+)"
    r"(?:(?:також|зараз|тоді|одразу)\s+)*(?:виправ\w*|пофікс\w*|внести правки)\b)", re.I
)
YES = re.compile(r"^\s*(?:yes|так|approve|approved|схвалюю|go ahead)[!.]?\s*$", re.I)
NO = re.compile(r"^\s*(?:no|ні|skip|пропустити)\b", re.I)
REDIRECT = re.compile(r"\b(?:i (?:only )?(?:asked|meant)|only asked for|я (?:лише |тільки )?(?:просив|мав на увазі)|"
                      r"цікавлять лише|цікавлять тільки|не це|не те)\b", re.I)
EXPECTED = re.compile(r"\b(?:expected|should|must|очіку\w*|має|повинен|повинна|потрібно щоб)\b", re.I)
FINDING = re.compile(r"\b(?:P[0-3]|findings?|blockers?|issues?|знахід\w*|блокер\w*|зауважен\w*)\b", re.I)
NO_FINDINGS = re.compile(r"\b(?:no (?:blocking )?(?:findings|blockers|issues)|без блокер\w*|блокер\w* не знайдено)\b", re.I)
REFERENCE = re.compile(r"\.[a-z0-9]{1,10}(?::|#L)\d+\b", re.I)
CAUSE = re.compile(r"\b(?:root cause|cause|причин\w*)\b", re.I)
QUESTION_BOUNDARY = re.compile(r"(?<=\?)")
ALTERNATIVES = re.compile(r"\b(?:or|або)\s+(?!not\s*\?)", re.I)


def edit_question(text):
    match = EDIT_OFFER.search(text)
    if match:
        return text[match.start():]
    if text.rstrip().endswith("?") and FIX.search(text):
        return text
    return ""


def reply_evidence(text):
    if "-----BEGIN " in text:
        return []
    short_reply = len(text) <= 150
    statement = ""
    lines, questions = [], []
    for line in text.splitlines():
        parts = []
        for part in QUESTION_BOUNDARY.split(line):
            offer = edit_question(part)
            if offer:
                questions.append(("question", offer))
                parts.append(part[:-len(offer)])
            elif part.rstrip().endswith("?"):
                questions.append(("other_question", ""))
            else:
                parts.append(part)
        line = "".join(parts)
        if short_reply:
            lines.append(line)
        elif not statement and len(line) <= 1200 and REFERENCE.search(line):
            if FINDING.search(line) or CAUSE.search(line):
                statement = line
    if short_reply:
        remaining = "\n".join(lines).strip()
        if FINDING.search(remaining) or CAUSE.search(remaining):
            statement = remaining
    edit_questions = [item for item in questions if item[0] == "question"]
    latest = edit_questions[-1:]
    if questions and (len(edit_questions) > 1 or questions[-1][0] == "other_question"):
        latest.append(("other_question", ""))
    return ([("assistant", statement)] if statement else []) + latest


def kind_for(session):
    first, *rest = session.turns
    request = first.request
    if REVIEW.search(request) and not FIX.search(request):
        kind = "review"
    elif FIX.search(request) or DEFECT.search(request) and FIX_QUESTION.search(request):
        kind = "bug_fix"
    else:
        return None
    return "mixed" if any(NEW_TASK.search(turn.request) for turn in rest) else kind


def events(session):
    for turn in session.turns:
        yield "user", turn.request
        position = 0
        for entry in turn.interaction:
            for action in turn.actions[position:entry.position]:
                yield "action", action
            yield entry.kind, entry
            position = entry.position
        for action in turn.actions[position:]:
            yield "action", action


def binary_offer(text):
    return not text.endswith("…") and not ALTERNATIVES.search(text)


def permission(role, value):
    if role == "answer":
        if not edit_question(value.question):
            return None
        if REVIEW_LIMIT.search(value.text) or (NO.search(value.text) and binary_offer(value.question)):
            return False
        if FIX.search(value.text) or (YES.search(value.text) and binary_offer(value.question)):
            return True
        return None
    if REVIEW_LIMIT.search(value):
        return False
    if FIX.search(value) or re.search(r"\b(?:review and fix|перевір і виправ|рев[’'ь]?ю і фікси)\b", value, re.I):
        return True
    return None


def review_case(session):
    criteria = dict.fromkeys(CRITERIA["review"], "unknown")
    allowed = None
    asked = False
    offer = None
    edit_permissions = set()
    steps, support = ["review_request"], []
    initial = session.turns[0].request
    if REVIEW_SCOPE.search(initial) or REVIEW_LIMIT.search(initial):
        criteria["review_scope"] = "observed"
        steps.append("scope")
    for role, value in events(session):
        if role in {"user", "answer"}:
            if role == "answer" and offer is not None:
                if offer.question_id and value.question_id:
                    if offer.question_id != value.question_id:
                        continue
                elif offer.text != value.question:
                    continue
            choice = permission(role, value)
            if role == "user" and choice is None and asked:
                choice = True if YES.search(value) else False if NO.search(value) else None
            if role == "user" or choice is not None:
                asked = False
            if choice is not None:
                allowed = choice
                if choice:
                    steps.append("approve")
                    support.append(value if role == "answer" else Interaction("answer", 0, excerpt(value)))
            if role == "user" and value != initial and REVIEW_SCOPE.search(value) and REDIRECT.search(value):
                steps.append("redirect")
                if criteria["review_scope"] != "observed":
                    criteria["review_scope"] = "gap"
        elif role in {"assistant", "question"}:
            if edit_question(value.text):
                offer = value
                asked = binary_offer(value.text)
                if allowed is True:
                    allowed = None
            elif role == "question":
                asked = False
            if role == "assistant" and FINDING.search(value.text) and not NO_FINDINGS.search(value.text):
                steps.append("findings")
                if REFERENCE.search(value.text):
                    criteria["review_evidence"] = "observed"
                    support.append(value)
        elif role == "other_question":
            asked = False
        elif role == "action":
            if value.kind in {"edit", "read", "test"}:
                steps.append("check" if value.kind == "test" else value.kind)
            if value.kind == "edit":
                if allowed is True:
                    edit_permissions.add("observed")
                elif allowed is False and not (session.skipped or session.compactions):
                    edit_permissions.add("gap")
                else:
                    edit_permissions.add("unknown")

    if edit_permissions:
        criteria["review_permission"] = next(status for status in ("gap", "unknown", "observed")
                                             if status in edit_permissions)
    elif session.client not in CHAT_CLIENTS and not session.skipped:
        criteria["review_permission"] = "not_applicable"
    return steps, criteria, support


def fix_case(session):
    criteria = dict.fromkeys(CRITERIA["bug_fix"], "unknown")
    steps, support = ["fix_request"], []
    before, after = set(), set()
    checked_since_edit = False
    for role, value in events(session):
        if role == "user" and "edit" not in steps and EXPECTED.search(value):
            criteria["fix_expected"] = "observed"
        elif role == "assistant" and "edit" not in steps and CAUSE.search(value.text) and REFERENCE.search(value.text):
            if "read" in steps or "check" in steps:
                criteria["fix_cause"] = "observed"
                steps.append("cause")
                support.append(value)
        elif role == "action" and value.kind in {"edit", "read", "test"}:
            if value.kind == "edit":
                after.clear()
                checked_since_edit = False
            elif value.kind == "test":
                checked_since_edit = "edit" in steps
                if value.signature:
                    (after if checked_since_edit else before).add(value.signature)
            steps.append("check" if value.kind == "test" else value.kind)

    if before & after:
        criteria["fix_recheck"] = "observed"
    elif before and "edit" in steps and not checked_since_edit:
        if not session.skipped and not session.compactions and session.turns[-1].outcome == "completed":
            criteria["fix_recheck"] = "gap"
    return steps, criteria, support


def analyze(session):
    kind = kind_for(session)
    if kind not in CRITERIA:
        return {"kind": kind or "unclassified"}

    steps, criteria, support = (review_case(session) if kind == "review" else fix_case(session))
    compact = []
    for step in steps:
        if not compact or compact[-1] != step:
            compact.append(step)
    return {"kind": kind, "steps": compact, "criteria": criteria, "support": support[:3]}


def path_steps(steps):
    return steps if len(steps) <= 12 else [*steps[:12], "continues"]


def summarize(sessions):
    cases = {session.id: analyze(session) for session in sessions if session.turns}
    groups = defaultdict(list)
    for case in cases.values():
        groups[case["kind"]].append(case)
    rows = []
    for kind, ids in CRITERIA.items():
        group = groups[kind]
        if not group:
            continue
        sequences = Counter(tuple(path_steps(case["steps"])) for case in group if len(case["steps"]) > 1)
        counts = {ident: Counter(case["criteria"][ident] for case in group) for ident in ids}
        rows.append({"kind": kind, "sessions": len(group),
                     "paths": [{"steps": list(steps), "count": count} for steps, count in sequences.most_common(3)],
                     "criteria": {ident: {key: counts[ident][key] for key in STATUSES} for ident in ids}})
    result = {"groups": rows, "mixed": len(groups["mixed"]), "unclassified": len(groups["unclassified"])}
    return result, cases
