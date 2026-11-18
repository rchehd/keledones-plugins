from __future__ import annotations

import json
import re
import sys
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from sessions import CHAT_CLIENTS, clean_request
from sources import Builder, obj, parse_ts, text_of

EXPORT_MEMBER = re.compile(r"conversations(?:-\d+)?\.json", re.IGNORECASE)


def export_documents(path):
    file = Path(path).expanduser()
    if file.suffix.lower() == ".json":
        with file.open("rb") as stream:
            yield json.load(stream)
        return

    if file.suffix.lower() != ".zip":
        raise ValueError("Use a ChatGPT or Claude JSON export, or its original ZIP")

    try:
        with zipfile.ZipFile(file) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()
                       and EXPORT_MEMBER.fullmatch(PurePosixPath(item.filename).name)]
            if not members:
                raise ValueError("ZIP contains no conversations JSON")
            for member in members:
                with archive.open(member) as stream:
                    yield json.load(stream)
    except (zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError("Cannot read conversations JSON from this ZIP") from error


def timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    return parse_ts(value)


def active_branch(conversation):
    nodes = obj(conversation.get("mapping"))
    node_id = conversation.get("current_node")
    if not node_id:
        parents = {node.get("parent") for node in nodes.values() if isinstance(node, dict)
                   and isinstance(node.get("parent"), str)}
        leaves = nodes.keys() - parents
        if len(leaves) != 1:
            return []
        node_id = next(iter(leaves))

    branch, visited = [], set()
    while isinstance(node_id, str) and node_id in nodes and node_id not in visited:
        visited.add(node_id)
        node = obj(nodes[node_id])
        branch.append(obj(node.get("message")))
        node_id = node.get("parent")
    return list(reversed(branch)) if node_id is None else []


def requests(conversation, client, sampled):
    if sampled:
        messages = conversation.get("messages")
        if isinstance(messages, list):
            for message in map(obj, messages):
                if message.get("role") == "user":
                    yield message.get("timestamp"), message.get("text")
    elif client == "chatgpt":
        for message in active_branch(conversation):
            if (obj(message.get("author")).get("role") != "user"
                    or obj(message.get("metadata")).get("is_visually_hidden_from_conversation")):
                continue
            content = obj(message.get("content"))
            parts = content.get("parts")
            if content.get("content_type") in ("text", "multimodal_text") and isinstance(parts, list):
                yield message.get("create_time"), "\n".join(part for part in parts if isinstance(part, str))
    else:
        for message in map(obj, conversation["chat_messages"]):
            if message.get("sender") in ("human", "user"):
                yield message.get("created_at"), text_of(message.get("content")) or message.get("text")


def read_conversation(conversation, client, sampled):
    ident = conversation.get("id") or conversation.get("conversation_id") or conversation.get("uuid")
    if not isinstance(ident, str) or not ident.strip():
        return None

    builder = Builder()
    for stamp, content in requests(conversation, client, sampled):
        moment = timestamp(stamp)
        request = clean_request(content) if isinstance(content, str) else ""
        if moment and request:
            builder.start(moment, request)
    if not builder.turns:
        return None

    builder.turns.sort(key=lambda turn: turn.ts)
    session = builder.build(client, ident, CHAT_CLIENTS[client])
    return replace(session, path=session.id)


def import_sources(exports=(), samples=()):
    sessions, stats = {}, {}

    def add(client, mode):
        entry = stats.setdefault(client, {"client": client, "found": True, "files": 0, "sessions": 0,
                                          "imports": [], "skipped_conversations": 0})
        if mode not in entry["imports"]:
            entry["imports"].append(mode)
        return entry

    def ingest(document, mode):
        sampled = mode == "sample"
        client = obj(document).get("source") if sampled else None
        records = document if isinstance(document, list) else obj(document).get("conversations")
        if not isinstance(records, list) or (sampled and (not isinstance(client, str) or client not in CHAT_CLIENTS)):
            raise ValueError("Unsupported chat history format")

        seen_sources = set()
        for record in map(obj, records):
            if not sampled:
                if isinstance(record.get("mapping"), dict):
                    client = "chatgpt"
                elif isinstance(record.get("chat_messages"), list):
                    client = "claude-chat"
                else:
                    continue

            seen_sources.add(client)
            entry = add(client, mode)
            session = read_conversation(record, client, sampled)
            if session is None:
                entry["skipped_conversations"] += 1
            else:
                existing = sessions.get(session.id)
                if existing is not None:
                    unique_turns = {(turn.ts, turn.request): turn for turn in [*existing.turns, *session.turns]}
                    session = with_turns(session, sorted(unique_turns.values(), key=lambda turn: turn.ts))
                sessions[session.id] = session

        if sampled:
            seen_sources.add(client)
        if not seen_sources and records:
            raise ValueError("No ChatGPT or Claude conversations recognized in the export")
        return seen_sources

    for path in dict.fromkeys(exports):
        clients = set()
        for document in export_documents(path):
            clients.update(ingest(document, "export"))
        for client in clients:
            stats[client]["files"] += 1

    for path in dict.fromkeys(samples):
        if path == "-":
            document = json.load(sys.stdin)
        else:
            with Path(path).expanduser().open("rb") as stream:
                document = json.load(stream)
        for client in ingest(document, "sample"):
            add(client, "sample")["files"] += 1

    for entry in stats.values():
        entry["sessions"] = sum(session.client == entry["client"] for session in sessions.values())
    return list(sessions.values()), list(stats.values())


def in_period(sessions, start, end):
    result = []
    for session in sessions:
        turns = []
        for turn in session.turns:
            day = turn.ts.astimezone().date()
            if (start is None or day >= start) and day <= end:
                turns.append(turn)
        if turns:
            result.append(with_turns(session, turns))
    return result


def with_turns(session, turns):
    return replace(session, turns=turns, started=turns[0].ts, ended=turns[-1].ts)
