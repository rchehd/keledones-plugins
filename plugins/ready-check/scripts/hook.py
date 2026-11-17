#!/usr/bin/env python3
import json
import os
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import answers
import hook_state
import logs
import rules
import settings
import tasks
from dependency_support import PLUGIN, asset_id, bundle_path, data_root, installed
from detect import FALLBACK
from fingerprint import last_checked, work_fingerprint
from profile_selection import argument, discover
from project import toplevel

EVENTS = ("session-start", "prompt", "answer", "stop")
CLIENTS = ("claude", "cursor", "codex")
CHECK = {"claude": "/ready:check", "cursor": "/check", "codex": "$check"}
RUNNERS = {"ddev": "DDEV", "compose": "Docker Compose", "local": "local"}
REMINDER = "If you have finished the user's task, ask once whether to run Ready Check ({check}); otherwise ignore this."


def session_id(payload):
    return str(payload.get("session_id") or payload.get("conversation_id") or "unknown")


def start_directory(payload):
    roots = payload.get("workspace_roots")
    return payload.get("cwd") or (roots[0] if isinstance(roots, list) and roots else None)


def template(name, **values):
    text = (PLUGIN / "hooks" / name).read_text(encoding="utf-8")

    for key, value in values.items():
        text = text.replace("{" + key + "}", value)

    return text.strip()


def browser_status():
    source = PLUGIN / "dependencies/browser"
    root = data_root()

    if installed(source, bundle_path(source, root, "browser")):
        return "ready"

    last = settings.read(root / "install-result.json")

    if last.get("status") == "FAIL" and last.get("bundle") == asset_id(source):
        return "failed"

    return "outdated" if any((root / "browser").glob("*/ready.json")) else "missing"


def status_line(status, client):
    if status != "failed":
        return f"Ready Check browser tools: {status}."

    last = settings.read(data_root() / "install-result.json")
    setup = {"claude": "/ready:setup", "cursor": "/setup", "codex": "$setup"}[client]
    return (f"Ready Check browser tools: failed ({last.get('reason')}; log: {last.get('log')}). "
            f"Tell the user once; they can retry with {setup} after fixing the cause.")


def quote(value):
    value = str(value)

    if os.name != "nt":
        return shlex.quote(value)

    if any(character in value for character in " &()[]{}^=;!'\"+,\x60~$|<>"):
        return "'" + value.replace("'", "''") + "'"
    return value


def command(top, decision, selected):
    parts = [sys.executable, PLUGIN / "scripts/ready-check.py", "consent", decision, "--project", top]

    for item in selected:
        parts += ["--selection", argument(item)]

    line = " ".join(quote(part) for part in parts)
    # PowerShell runs a quoted executable path only through the call operator.
    return "& " + line if os.name == "nt" and line.startswith("'") else line


def describe(found):
    name = found["name"] + (" " + found["version"] if found["version"] else "")
    where = "" if found["application"] == "." else f" in {found['application']}/"
    return f"{name}{where}, {RUNNERS.get(found['runner'], found['runner'])}"


def question(selected, conflicts, values, status, confirmed):
    project = "; ".join(describe(item) for item in selected)
    downloads = []

    if status != "ready" and values["install"] != "never":
        downloads.append("Playwright and Chromium (about 200 MB, once per machine)")

    if not confirmed and values["install"] != "never":
        checkers = sorted({item["name"] for item in selected if item["profile"] != FALLBACK})
        if checkers:
            downloads.append(f"the {', '.join(checkers)} checkers if they are not installed yet")

    if confirmed and values["install"] == "auto":
        return "Ready Check tools are missing or outdated. Run the accept command now without asking."

    if confirmed:
        return (f"Ask the user once, in their language: \"Ready Check needs {' and '.join(downloads)}. Install?\" "
                "On yes run the accept command, on no run the decline command.")

    text = f"Ask the user once, in their language: \"Ready Check detected: {project}."
    evidence = [f"{item['profile']} in {item['application']}: {', '.join(item['evidence'])}"
                for item in selected if item["evidence"]]
    if evidence:
        text += f" Signals: {'; '.join(evidence)}."
    if conflicts:
        roots = ", ".join(item["application"] for item in conflicts)
        text += f" Confirm which profiles apply in {roots}. Run only the confirmed --selection arguments."

    if downloads and values["install"] == "ask":
        return text + f" To work it needs {' and '.join(downloads)}. Install? Correct the project type if it is wrong.\""

    if downloads:
        return text + f" Is this correct?\" After confirmation run the accept command; it installs {' and '.join(downloads)}."

    decision = "decline" if values["install"] == "never" else "accept"

    return text + f" Is this correct?\" Then run the {decision} command."


def first_run(top, client, values, status):
    raw = settings.read(settings.project_path(top))
    confirmed = settings.valid("profiles", raw.get("profiles")) or settings.valid("runner", raw.get("runner"))
    pending_download = status not in {"ready", "failed"} and values["install"] != "never"

    if confirmed and not pending_download:
        return None

    try:
        _, selected, conflicts = discover(top)
    except (OSError, ValueError) as error:
        return f"Ready Check profile setup is unresolved ({error}). Ask the user to correct it with the setup skill."

    fallback = "; in Claude Code the user can run it by typing ! followed by the command" if client == "claude" else ""
    return template("first-run.md", question=question(selected, conflicts, values, status, confirmed), fallback=fallback,
                    yes=command(top, "yes", selected), no=command(top, "no", selected), language=language_note(values))


def language_note(values):
    if "artifactLanguage" in settings.read(settings.user_path()):
        return ""

    config = f"{quote(sys.executable)} {quote(PLUGIN / 'scripts/ready-check.py')} config set artifactLanguage"
    return (f"In the same question add one line: Ready Check writes its reports and other files in {values['artifactLanguage']}; "
            f"another language can be chosen. If the user names one, run `{config} \"<language in English>\"`.\n\n")


def session_start(client, payload):
    top = toplevel(start_directory(payload)) if start_directory(payload) else None
    values = settings.load(top)
    hook_state.prune()
    status = browser_status()
    rules_command = f"{quote(sys.executable)} {quote(PLUGIN / 'scripts/ready-check.py')} rules add"
    parts = [template("session-rule.md", check=CHECK[client], rules=rules_command, language=values["artifactLanguage"]),
             status_line(status, client)]
    coding_rules = rules.context(top)

    if coding_rules:
        parts.append(coding_rules)

    if top:
        tasks.prune(top)
        state = hook_state.load(client, session_id(payload))

        if "start" not in state:
            hook_state.save(client, session_id(payload), dict(state, start=work_fingerprint(top)))
        request = first_run(top, client, values, status)

        if request:
            parts.append(request)

    text = "\n\n".join(parts)

    if client == "cursor":
        return {"additional_context": text}

    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def prompt(client, payload):
    directory = start_directory(payload)
    top = toplevel(directory) if directory else None

    if top and settings.load(top)["captureTasks"]:
        tasks.record(top, client, session_id(payload), payload.get("prompt"))


def answer(client, payload):
    directory = start_directory(payload)
    top = toplevel(directory) if directory else None
    text = answers.text(payload) if top else None

    if text and settings.load(top)["captureTasks"]:
        tasks.record(top, client, session_id(payload), text)


def stop(client, payload):
    directory = start_directory(payload)
    top = toplevel(directory) if directory else None

    if not top or payload.get("stop_hook_active") is True or not settings.load(top)["remind"]:
        return None

    session = session_id(payload)
    state = hook_state.load(client, session)
    current = work_fingerprint(top)

    if "start" not in state:
        hook_state.save(client, session, dict(start=current))
        return None

    if current in {state.get("start"), state.get("reminded"), last_checked(top)}:
        return None

    hook_state.save(client, session, dict(state, reminded=current))
    text = REMINDER.format(check=CHECK[client])

    if client == "codex":
        return {"decision": "block", "reason": text}

    return {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": text}}


def allow(event, client):
    return {"continue": True} if event == "prompt" and client == "cursor" else None


def handle(event, client, payload):
    try:
        if event == "session-start":
            return session_start(client, payload)

        if event == "stop":
            return stop(client, payload)

        if event == "answer":
            answer(client, payload)
            return None

        prompt(client, payload)
    except Exception as error:
        logs.error(f"{client} {event} hook failed: {type(error).__name__}: {error}")

    return allow(event, client)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    event = argv[0] if argv else None
    client = argv[argv.index("--client") + 1] if "--client" in argv[:-1] else None

    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        payload = json.loads(raw) if raw.strip() else {}
        payload = payload if isinstance(payload, dict) else {}
    except (OSError, ValueError) as error:
        logs.error(f"Unreadable hook input: {error}")
        payload = {}

    if event not in EVENTS or client not in CLIENTS:
        logs.error(f"Unknown hook call: {argv}")
        output = None
    else:
        output = handle(event, client, payload)

    if output:
        sys.stdout.write(json.dumps(output) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
