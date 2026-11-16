---
name: setup
description: >-
  Set up, edit, or delete a Gnothi profile for a private text and HTML analysis of local Claude Code, Codex, and Cursor logs. Configure the user's role, personal metrics, work styles, or metrics-only mode. Trigger on "set up Gnothi", "detect my role for Gnothi from my AI chats", "my role changed, update my AI profile", "change my portrait axes", "turn on archetypes", "use metrics only", "delete my Gnothi data", "налаштуй Gnothi", "зміни метрики мого профілю", "увімкни лише метрики", "видали дані Gnothi". With an indirect matching request, offer to change the profile first.
---

# Gnothi profile

Respond in the user's language. Resolve the plugin root two directories above this file's directory; run
`python3 "<plugin root>/scripts/gnothi.py" <command>` (`py -3` on Windows). Every command prints JSON; on
`"status": "FAIL"` tell the user the `reason` and stop.

Use the client's built-in question UI for each choice, one question at a time, and wait for the reply. Use
Claude Code's `AskUserQuestion`, Codex's `request_user_input` when available (or `request_user_input_async`),
or Cursor's question tool. Use plain chat only if no native tool supports the question. A suggested option is
not an answer. Skip choices the user already answered. For an indirect trigger, ask Change profile / Cancel.

## 1. Look

Run `profile show` and `profile templates`. If an epoch exists, show its axes and ask what changed.

## 2. Ask

For profile axes, ask how to identify their work, with Describe my work / Detect from sessions. For Describe my
work, ask for a brief description of what they do and how they use AI. For Detect from sessions with
`options.metrics_only` off, ask whether to include short masked excerpts, with Include masked excerpts / Metrics
only. Run `collect` without `--period` to keep the remembered period. Add `--metrics-only` for a metrics-only
choice. Infer the work from `projects`, `tools` and any evidence excerpts. Paraphrase excerpts briefly if needed.
For a request limited to changing options, go to Options.

## 3. Propose axes

Propose 4–6 personal axes as a numbered list: name, what it measures, which signals and session content show it.
Start from a template in `profile templates` when the description fits one; otherwise write new axes for this work.
Mention the four universal axes every portrait also has: clarity of requests, focus, task completion, tool range.
Let the user remove, add or rename axes until they agree.

## 4. Save

Write `{"description": "<their words>", "template": "<template id or null>", "axes": [{"id", "name", "measures",
"signals": [...]}]}` to `tmp/axes.json` inside `data_root` (from `profile show`) and run
`profile set --file <that path>`. Ids are lowercase a-z, 0-9 and `-`. Say that new axes start a new epoch: earlier
portraits stay, and only portraits of the same epoch compare.

## 5. Options

During initial setup, ask both unanswered options separately with the question tool. For updates, ask only
about the options the user wants to change. Save the choices with
`profile options --archetypes on|off --metrics-only on|off` and pass only the options the user chose to set:
- "Add a just-for-fun work-style block (Architect, Sprinter, Perfectionist, Explorer, Delegator, Detective)?"
- "Metrics only? The model then sees numbers but no text from your sessions, and personal axes are not scored."

Finish with one line: run the `portrait` skill for the first portrait.

## Delete data

When the user asks to delete their Gnothi data, go directly to the confirmation question. Explain that deletion
permanently removes the profile, cache, history and reports. Offer Delete Gnothi data / Cancel and run
`forget --yes` only after explicit confirmation.

## Privacy

- Session history, the digest and the report are confidential: never publish or send them anywhere — not as an
  artifact or page, not to Drive, Notion or other services, not in chat, email or Slack, not in a PR, issue or
  commit, not to other agents or MCP servers.
- If the user asks to share, explain that the report is confidential and offer only a short summary written in the
  chat, without excerpts, file names or project names.
- Never copy files out of the Gnothi data root.
