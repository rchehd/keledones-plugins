from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from redact import excerpt, redact
from sessions import Interaction, Session, Turn, classify, session_id
from workflows import reply_evidence

DETAIL_KEYS = ("command", "cmd", "skill", "file_path", "path", "target_file")
QUESTION_TOOLS = {"askuserquestion", "request_user_input", "request_user_input_async", "askquestion", "ask_question"}
UI_REPLY = re.compile(r"<send_user_message_question_reply>\s*(.*?)\s*</send_user_message_question_reply>", re.S)
CLAUDE_ANSWER = re.compile(r'"((?:[^"\\]|\\.)+)"\s*=\s*"((?:[^"\\]|\\.)*)"')


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


def decode(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def question_identity(call_id, index):
    identity = json.dumps([call_id, index]).encode()
    return hashlib.sha256(identity).hexdigest()


class Builder:
    def __init__(self):
        self.turns, self.times = [], []
        self.skipped = self.compactions = 0
        self.questions = {}
        self.cwd = ""

    @property
    def current(self):
        return self.turns[-1] if self.turns else None

    def seen(self, moment):
        if moment:
            self.times.append(moment)

    def start(self, moment, request):
        self.seen(moment)
        self.turns.append(Turn(moment, redact(request)))

    def act(self, tool, value=None, call_id=None):
        if self.current:
            fields = obj(decode(value))
            workdir = fields.get("workdir") or fields.get("cwd") or fields.get("working_directory")
            self.current.actions.append(classify(tool, detail(value),
                                                 workdir=workdir if isinstance(workdir, str) else "", cwd=self.cwd))
            if tool.casefold() in QUESTION_TOOLS:
                questions = fields.get("questions")
                if isinstance(call_id, str) and call_id:
                    self.questions[call_id] = questions
                for index, item in enumerate(questions if isinstance(questions, list) else []):
                    if isinstance(item, dict):
                        ident = question_identity(call_id, index) if call_id else ""
                        self.visible("question", item.get("question") or item.get("prompt") or item.get("text"),
                                     question_id=ident)

    def visible(self, kind, text, question="", *, question_id=""):
        if not self.current or not isinstance(text, str) or not text.strip():
            return
        entries = self.current.interaction
        if len(str(question or "")) > 4096:
            return
        excerpts = reply_evidence(text) if kind == "assistant" else [(kind, text)]
        for event_kind, snippet in excerpts:
            if len(entries) >= 12:
                break
            if len(snippet) <= 4096:
                current = Interaction(event_kind, len(self.current.actions), excerpt(snippet), excerpt(question), question_id)
                if current not in entries:
                    entries.append(current)

    def menu_reply(self, text):
        match = UI_REPLY.fullmatch(text.strip())
        if not match:
            return False
        items = decode(match[1])
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                key = decode(item.get("questionItemId"))
                ident = (question_identity(key[1], key[2]) if isinstance(key, list) and len(key) == 3
                         and isinstance(key[1], str) and type(key[2]) is int else "")
                self.visible("answer", item.get("answer"), item.get("question"), question_id=ident)
        return True

    def tool_answer(self, call_id, value):
        if not isinstance(call_id, str):
            return
        questions = self.questions.pop(call_id, None)
        if not isinstance(questions, list):
            return
        prompts = {}
        for index, item in enumerate(questions):
            if not isinstance(item, dict):
                continue
            text = item.get("question") or item.get("prompt") or item.get("text") or ""
            options = item.get("options")
            labels = {str(entry.get("id", entry.get("label"))): str(entry.get("label") or entry.get("id") or "")
                      for entry in options if isinstance(entry, dict)} if isinstance(options, list) else {}
            prompts[str(item.get("id", index))] = prompts[str(text)] = (str(text), labels, question_identity(call_id, index))

        data = decode(text_of(value) if isinstance(value, list) else value)
        answers = obj(data).get("answers", obj(obj(data).get("outcome")).get("answers"))
        if isinstance(answers, dict):
            pairs = answers.items()
        elif isinstance(answers, list):
            pairs = ((item.get("questionId", item.get("id")), item) for item in answers if isinstance(item, dict))
        elif isinstance(data, str) and data.startswith("Your questions have been answered"):
            pairs = CLAUDE_ANSWER.findall(data)
        else:
            return

        for key, answer in pairs:
            question, labels, ident = prompts.get(str(key), ("", {}, ""))
            if isinstance(answer, dict):
                answer = answer.get("answers", answer.get("selectedOptionIds", answer.get("answer")))
            if isinstance(answer, list):
                answer = ", ".join(labels.get(entry, entry) for entry in answer if isinstance(entry, str))
            if question:
                self.visible("answer", answer, question, question_id=ident)

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
