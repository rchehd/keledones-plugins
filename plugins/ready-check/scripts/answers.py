import json
import re

# Question tools: Claude Code AskUserQuestion, Codex request_user_input, Cursor ask_question.
QUESTION_TOOL = re.compile(r"ask.?user.?question|request.?user.?input|ask.?question", re.I)
ANSWERED_TEXT = re.compile(r'"((?:[^"\\]|\\.)+)"\s*=\s*"((?:[^"\\]|\\.)*)"')


def is_question_tool(name):
    return isinstance(name, str) and bool(QUESTION_TOOL.search(name))


def parsed(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value

    return value


def questions(tool_input):
    found = {}

    for index, item in enumerate((tool_input or {}).get("questions") or []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("question") or item.get("prompt") or item.get("text") or item.get("header") or "").strip()
        labels = {str(option.get("id", option.get("label"))): str(option.get("label") or option.get("id"))
                  for option in item.get("options") or [] if isinstance(option, dict)}
        found[str(item.get("id", index))] = (text, labels)

    return found


def chosen(value, labels):
    if isinstance(value, dict):
        value = value.get("answers", value.get("selectedOptionIds", value.get("answer", value.get("selected", ""))))

    values = value if isinstance(value, list) else [value]
    return ", ".join(labels.get(str(item), str(item)) for item in values if str(item).strip())


def pairs(tool_input, response):
    asked = questions(tool_input)
    by_text = {text: labels for text, labels in asked.values()}
    result = []

    for source in (response, tool_input):
        source = parsed(source)

        if isinstance(source, dict):
            source = source.get("answers", source.get("outcome", {}).get("answers") if isinstance(source.get("outcome"), dict) else None)

        if isinstance(source, dict):
            for key, value in source.items():
                text, labels = asked.get(str(key), (str(key), by_text.get(str(key), {})))
                result.append((text, chosen(value, labels)))
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    key = str(item.get("questionId", item.get("id", item.get("question", ""))))
                    text, labels = asked.get(key, (str(item.get("question") or key), {}))
                    result.append((text, chosen(item, labels)))
        elif isinstance(source, str):
            result.extend((q, a) for q, a in ANSWERED_TEXT.findall(source))

        if result:
            return result

    return result


def text(payload):
    if not is_question_tool(payload.get("tool_name")):
        return None
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    response = payload.get("tool_response", payload.get("tool_output"))
    lines = [f"Q: {q.strip()}\nA: {a.strip()}" for q, a in pairs(tool_input, response) if q.strip() and a.strip()]
    return "\n".join(lines) or None
