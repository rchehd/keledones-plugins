---
name: portrait
description: >-
  Build a private portrait of how the user gives instructions, delegates, clarifies and redirects AI agents.
  Trigger on "show my AI work portrait", "review my chats with ChatGPT or Claude", "analyze my Codex history",
  "look at my Cursor sessions", "how good am I at prompting", "stats of my AI usage", "self-reflection on my work
  with AI", "show my typical workflow with agents", "як я працюю з ШІ", "проаналізуй мої чати з агентами",
  "покажи мій типовий воркфлоу з агентами", or "що я роблю не так у промптах".
  An explicit Gnothi request starts the workflow. For an indirect match, offer Gnothi first. Clarify broad
  requests about typical mistakes before selecting a workflow.
---

# Gnothi portrait

Respond and write the portrait in the user's language. Use the [chat history instructions](references/chat-history.md)
to discover accessible sources and choose the report format. If the client cannot run the bundled script against
the user's local machine, follow **Portrait in chat** in that reference. A cloud shell does not grant access to a
user's computer. On the local path, resolve the plugin root two directories above this file's directory and run
`python3 "<plugin root>/scripts/gnothi.py" <command>` (`py -3` on Windows). Commands print JSON; report a
`"status": "FAIL"` with its `reason`. Use the digest for the local report.
If the user only asks what Gnothi can do, explain that it analyzes available agent sessions and ordinary chats.
Offer to run it. Treat an affirmative follow-up as the user's choice to proceed with this workflow.

If a request such as "show my typical mistakes" or "покажи мої типові помилки" is ambiguous, ask whether the user means their interaction
with agents or recurring gaps in preparing tasks for PR. Wait for their choice before reading history.
Use this portrait for the former and offer Ready Check's `reflect` for the latter if it is available.

Use the client's built-in question UI for every choice, one question at a time, and wait for the reply. Use
Claude Code's `AskUserQuestion`, Codex's `request_user_input` when available (or `request_user_input_async`),
or Cursor's question tool. Use plain chat only if no native tool supports the question. A suggested option is
not an answer. For an indirect trigger, ask Run Gnothi / Cancel through the same UI.

## 1. Profile and period

For a local report, run `storage-check` before profile setup or collection. If it fails, follow
[Private storage access](references/chat-history.md#private-storage-access). Run `profile show`. Without an
epoch (and without the metrics-only option), follow the `setup` skill first for the HTML report.
Ask for the period if the user has not given it. Offer all history (`all`), last year (`year`), last 6 months
(`half`), and last month (`month`), with the remembered one (`options.period`) first. If the question tool
accepts only three options, offer the remembered period or Choose another period, then offer the other three.

## 2. Collect

Discover available chat inputs using the reference. Run `collect --period <period>` with any applicable
`--chat-export` or `--chat-sample` flags. Add `--metrics-only` only if the user asks for it this time. Read the JSON:
`sources` (what was found, how many sessions), `current` and `previous` (signals, universal axes, archetypes),
`trend`, `activity`, `tools`, `friction`, `tokens`, `projects`, `workflow` and `evidence` (session ids, flags and redacted
excerpts). If no sessions were found, state what was accessible and offer a specific supported chat input.
Let the script read raw local history and exports. When metrics-only is active, leave native conversation retrieval
off unless the host supplies aggregate counts; offer a local export for chat counts without exposing message text.
For a portrait in chat from local sources without saving files, add `--no-save` and follow
[Private storage access](references/chat-history.md#private-storage-access). Check `metrics_only` in the returned digest.

## 3. Write `portrait.json`

Write it next to the digest (`tmp/portrait.json` in the data root, the folder of `digest`):

```json
{"schema_version": 1, "language": "<language code>", "summary": "<2–3 sentences>",
 "axes": [{"id": "<profile axis id>", "name": "<localized name>", "measures": "<localized meaning>",
           "score": 0-10 or null, "reason": "<what raised or lowered the score>", "evidence": ["<session id>"]}],
 "strengths": [{"title": "", "detail": "", "evidence": ["<id>", "<id>"], "cause": "<optional>"}],
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
- Include every axis of the current epoch exactly once, using its signals and the excerpts; compare with the previous
  period's numbers where they exist. Scores describe this person against their own past, not an ideal.
  In each reason, name the observed behavior or count that raised or lowered the score. When chat history
  contributes to the sample and an axis has insufficient evidence, use `null` and say what evidence is missing.
- For verification habits, use `checks_after_edit_sessions` out of `edit_sessions` when edits were recorded.
  These counts describe logged check calls. Claims about check results require separate evidence.
- Chat history contributes user requests and their timestamps. Use the agent-log scope for tool, verification,
  elapsed time, focus, completion and work-style metrics. Compare periods only where their source coverage supports it.
- Strengths and growth: 3–5 each when the data allows, never more than 5. Each needs at least two evidence
  sessions, or one session plus a clear `cause`. Anything weaker goes to `observations`.
- Follow [workflow analysis](references/workflow-analysis.md) when interpreting common sequences and criteria.
  Put supported insights in the existing strengths or growth fields, with the optional `criterion` ID.
  The HTML block renders counts and paths directly from the digest.
- For a strength, describe the effective behavior and support it with evidence.
- For an area to grow, give one concrete next step, such as naming the file and expected result in the first request.
- `archetype` only when `current.archetypes` is not null: pick the highest score as lead and the next one as
  second when it is within 1.5 points; explain with numbers ("70% of sessions started from a plan").
- `coverage.uncovered_share`: the share of the period's work that fits none of the personal axes.
- Metrics-only digest: `axes` is `[]`, findings have no evidence and each needs a `cause` quoting the numbers.

## 4. Render

Run `render`. If storage access fails here or at another local step, follow
[Private storage access](references/chat-history.md#private-storage-access). For other failures, fix what
`reason` lists and run it again. Pass on `warnings` in one line.

For a requested aggregate-only HTML view, run `render --widget-metrics <digest_id>` using the approved
collection's ID. If it no longer matches, collect the selected data and confirm the period again. Give the
returned `widget_html` path. It contains the selected period's metrics and the previous period for comparison.
The full private report is at `html`.

## 5. Reply

Use the [Markdown portrait template](../../templates/portrait.md) in the current private chat. Fill it
from the current digest and supported findings, keeping its section order and translating the display
text. Pair each finding with a concise paraphrase or aggregate count. Suggest a concrete change and a
way to check it in a later period. State when a comparison cannot be made. Give the report path from
`html` to open in a browser. Give the count for each source and mark exports and retrieved samples.
When the workflow evidence supports it, include one common interaction sequence or concrete point of friction.

## Privacy

- Keep source history, digests and local reports private. Only give the user a short, paraphrased portrait in the
  current private chat when using the chat route. Avoid external services, published artifacts and repository files.
- If the user asks to share, explain that the report is confidential and offer only a short summary written in the
  chat, without excerpts, file names or project names.
- Quote at most short paraphrases of excerpts in the chat. Never copy files out of the Gnothi data root.
