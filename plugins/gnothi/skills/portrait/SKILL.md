---
name: portrait
description: >-
  Run Gnothi to analyze local Claude Code, Codex, and Cursor session history and write a private text and offline HTML report on how the user works with AI agents. This is session analysis, never an image. Trigger on "show my AI work portrait", "review my chats with Claude", "analyze my Codex history", "look at my Cursor sessions", "my habits or style with agents", "how good am I at prompting", "what do I do wrong with AI", "stats of my AI usage", "self-reflection on my work with AI", "як я працюю з ШІ", "проаналізуй мої чати з агентами", "що я роблю не так у промптах", "покажи статистику моєї роботи з AI". An explicit request for a Gnothi report starts the workflow. With an indirect matching request, offer to run Gnothi first.
---

# Gnothi portrait

Respond and write the portrait in the user's language. Resolve the plugin root two directories above this file's
directory; run `python3 "<plugin root>/scripts/gnothi.py" <command>` (`py -3` on Windows). Every command prints
JSON; on `"status": "FAIL"` tell the user the `reason` and stop. The script counts; you read, group and write.
Always run the bundled script for a Gnothi report. Generate the analysis from its digest. Never generate an image
or substitute general knowledge, chat memory, or a personality portrait. If the script is unavailable, report the blocker.
If the user only asks what Gnothi can do, explain that it analyzes local sessions into a text and HTML report.
Offer to run it. Treat an affirmative follow-up as the user's choice to proceed with this workflow.

Use the client's built-in question UI for every choice, one question at a time, and wait for the reply. Use
Claude Code's `AskUserQuestion`, Codex's `request_user_input` when available (or `request_user_input_async`),
or Cursor's question tool. Use plain chat only if no native tool supports the question. A suggested option is
not an answer. For an indirect trigger, ask Run Gnothi / Cancel through the same UI.

## 1. Profile and period

Run `profile show`. Without an epoch (and without the metrics-only option), follow the `setup` skill first.
Ask for the period if the user has not given it. Offer all history (`all`), last year (`year`), last 6 months
(`half`), and last month (`month`), with the remembered one (`options.period`) first. If the question tool
accepts only three options, offer the remembered period or Choose another period, then offer the other three.

## 2. Collect

Run `collect --period <period>` (add `--metrics-only` only if the user asks for it this time). Read the JSON:
`sources` (what was found, how many sessions), `current` and `previous` (signals, universal axes, archetypes),
`trend`, `activity`, `tools`, `friction`, `tokens`, `projects` and `evidence` (session ids, flags and redacted
excerpts). No sessions → say so and stop. Never open the raw session files.

## 3. Write `portrait.json`

Write it next to the digest (`tmp/portrait.json` in the data root, the folder of `digest`):

```json
{"schema_version": 1, "language": "<language code>", "summary": "<2–3 sentences>",
 "axes": [{"id": "<profile axis id>", "name": "<localized name>", "measures": "<localized meaning>",
           "score": 0-10, "reason": "<what raised or lowered the score>", "evidence": ["<session id>"]}],
 "strengths": [{"title": "", "detail": "", "tip": "", "evidence": ["<id>", "<id>"], "cause": "<optional>"}],
 "growth": [{"title": "", "detail": "", "tip": "", "evidence": ["<id>", "<id>"], "cause": "<optional>"}],
 "observations": [{"title": "", "detail": ""}],
 "themes": [{"project": "<name from projects>", "topics": ["<short topic>"]}],
 "archetype": {"lead": "<archetype>", "second": "<archetype or null>", "text": "<2–3 sentences>"} or null,
 "coverage": {"uncovered_share": 0-1, "note": "<what the axes miss>"}}
```

Rules:
- Use the chat language for all authored text, including axis names and descriptions from the profile. Keep axis
  IDs, project names and evidence IDs from the input. For any language other than English, run `ui-strings`,
  translate all values in `strings` into the chat language, and put them in `portrait.json` under `ui`.
  Keep every key and every `{placeholder}` intact. Use plain text for labels.
- Score every axis of the current epoch exactly once, from its signals and the excerpts; compare with the previous
  period's numbers where they exist. Scores describe this person against their own past, not an ideal.
  In each reason, name the observed behavior or count that raised or lowered the score.
- For verification habits, use `checks_after_edit_sessions` out of `edit_sessions` when edits were recorded.
  These counts describe logged check calls. Claims about check results require separate evidence.
- Strengths and growth: 3–5 each when the data allows, never more than 5. Each needs at least two evidence
  sessions, or one session plus a clear `cause`. Anything weaker goes to `observations`.
- Tips are concrete next steps ("name the file and the expected result in the first request"), not slogans.
- `archetype` only when `current.archetypes` is not null: pick the highest score as lead and the next one as
  second when it is within 1.5 points; explain with numbers ("70% of sessions started from a plan").
- `coverage.uncovered_share`: the share of the period's work that fits none of the personal axes.
- Metrics-only digest: `axes` is `[]`, findings have no evidence and each needs a `cause` quoting the numbers.

## 4. Render

Run `render`. On FAIL fix exactly what `reason` lists and run it again. Pass on `warnings` in one line.

## 5. Reply

5–8 lines: the summary, the top strengths and growth areas, the biggest change against the previous period, and the
report path from `html` to open in a browser. Mention when Cursor tokens are not counted.

## Privacy

- Session history, the digest and the report are confidential: never publish or send them anywhere — not as an
  artifact or page, not to Drive, Notion or other services, not in chat, email or Slack, not in a PR, issue or
  commit, not to other agents or MCP servers.
- If the user asks to share, explain that the report is confidential and offer only a short summary written in the
  chat, without excerpts, file names or project names.
- Quote at most short paraphrases of excerpts in the chat. Never copy files out of the Gnothi data root.
