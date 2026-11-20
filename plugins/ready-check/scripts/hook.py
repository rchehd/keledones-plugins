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
from detect import has_managed_tools
from draft_template import client_comment_template
from fingerprint import last_checked, work_fingerprint
from profile_selection import argument, discover
from project import migrate, project_file, toplevel

EVENTS = ("session-start", "prompt", "answer", "stop")
CLIENTS = ("claude", "cursor", "codex")
CHECK = {"claude": "/ready:check", "cursor": "/check", "codex": "$check"}
RUNNERS = {"ddev": "DDEV", "compose": "Docker Compose", "local": "local"}
OFFER = PLUGIN / "skills/check/references/check-offer.md"
REMINDER = ("If you have finished the user's task and the user has not turned Ready Check off for this session, "
            "ask once about Ready Check ({check}) with the choices in `{offer}`: all checks, static + review, QA only, "
            "or turn off for this session. Use {question} when available. A yes/no prompt alone is insufficient.")
QUESTION_TOOL = {"claude": "AskUserQuestion", "codex": "request_user_input or request_user_input_async"}
# Claude Code drops additionalContext over 10,000 characters to a file the model is not told to read.
CONTEXT_LIMIT = 9500


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


def posix(client):
    # Claude Code runs commands in Git Bash on Windows when it is installed; Git Bash sets MSYSTEM.
    return os.name != "nt" or client == "claude" and bool(os.environ.get("MSYSTEM"))


def quote(value, client):
    value = str(value)

    if posix(client):
        return shlex.quote(value)

    if any(character in value for character in " &()[]{}^=;!'\"+,\x60~$|<>"):
        return "'" + value.replace("'", "''") + "'"
    return value


def shell_command(parts, client):
    line = " ".join(quote(part, client) for part in parts)
    # PowerShell runs a quoted executable path only through the call operator.
    return "& " + line if not posix(client) and line.startswith("'") else line


def command(top, decision, selected, client):
    parts = [sys.executable, PLUGIN / "scripts/ready-check.py", "consent", decision, "--project", top]

    for item in selected:
        parts += ["--selection", argument(item)]

    return shell_command(parts, client)


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
        checkers = sorted({item["name"] for item in selected if has_managed_tools(item["profile"])})
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
    raw = settings.read(project_file(top, "settings.json"))
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
                    yes=command(top, "yes", selected, client), no=command(top, "no", selected, client),
                    language=language_note(values, client))


def language_note(values, client):
    if "artifactLanguage" in settings.read(settings.user_path()):
        return ""

    config = shell_command([sys.executable, PLUGIN / "scripts/ready-check.py", "config", "set", "artifactLanguage"], client)
    return (f"In the same question add one line: Ready Check writes its reports and other files in {values['artifactLanguage']}; "
            f"another language can be chosen. If the user names one, run `{config} \"<language in English>\"`.\n\n")


def session_context(client, payload, top):
    migration_error = None
    try:
        migrate(top)
    except (OSError, ValueError, RuntimeError) as error:
        migration_error = str(error)[:500]
    values = settings.load(top)
    hook_state.prune()
    status = browser_status()
    entry = [sys.executable, PLUGIN / "scripts/ready-check.py"]
    comment_template = client_comment_template()
    comment_option = (" " + quote("--client-template=" + comment_template, client)
                      if settings.valid("taskCommentTemplate", comment_template) else "")
    offers_off = shell_command([*entry, "offers", "off", "--client", client, "--session", session_id(payload)], client)
    rule = template("session-rule.md", check=CHECK[client], rules=shell_command([*entry, "rules", "add"], client),
                    template_command=shell_command([*entry, "template"], client), comment_option=comment_option,
                    language=values["artifactLanguage"], offer=OFFER.as_posix(), offers_off=offers_off)
    tasks.prune(top)

    if "start" not in hook_state.load(client, session_id(payload)):
        try:
            start = work_fingerprint(top)
            # Reload right before saving: Cursor runs sessionStart and the first prompt at the same time.
            hook_state.save(client, session_id(payload), dict(hook_state.load(client, session_id(payload)), start=start))
        except ValueError as error:
            logs.error(f"{client} session-start fingerprint skipped: {error}")

    parts = [first_run(top, client, values, status), rules.context(top), rule, status_line(status, client)]

    if migration_error:
        parts.append(f"Ready Check project data migration could not complete: {migration_error}")

    text = "\n\n".join(part for part in parts if part)

    if len(text) > CONTEXT_LIMIT and parts[1]:
        parts[1] = ("Ready Check coding rules are too long for the session context. Read them with "
                    f"`{shell_command([*entry, 'rules', 'list', '--project', top], client)}` before writing code; "
                    "the Ready Check review checks changed code against them (MUST rules block).")
        text = "\n\n".join(part for part in parts if part)

    return text


def session_start(client, payload):
    top = toplevel(start_directory(payload)) if start_directory(payload) else None

    if not top:
        return None

    text = session_context(client, payload, top)

    if client == "cursor":
        return {"additional_context": text}

    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def prompt(client, payload):
    directory = start_directory(payload)
    top = toplevel(directory) if directory else None

    if not top:
        return None

    if settings.load(top)["captureTasks"]:
        tasks.record(top, client, session_id(payload), payload.get("prompt"))

    # Cursor may drop sessionStart context that arrives after the chat's first request, so the first prompt repeats it.
    if client != "cursor" or hook_state.load(client, session_id(payload)).get("context"):
        return None

    text = session_context(client, payload, top)
    hook_state.save(client, session_id(payload), dict(hook_state.load(client, session_id(payload)), context=True))
    return {"continue": True, "additional_context": text}


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

    if state.get("off"):
        return None

    current = work_fingerprint(top)

    if "start" not in state:
        hook_state.save(client, session, dict(start=current))
        return None

    if current in {state.get("start"), state.get("reminded"), last_checked(top)}:
        return None

    hook_state.save(client, session, dict(hook_state.load(client, session), reminded=current))
    text = REMINDER.format(check=CHECK[client], offer=OFFER.as_posix(),
                           question=QUESTION_TOOL.get(client, "the client's question tool"))

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

        output = prompt(client, payload)

        if output:
            return output
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
