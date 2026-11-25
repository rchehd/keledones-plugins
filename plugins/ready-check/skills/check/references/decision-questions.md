# Decisions during Ready Check

Post the context as a standalone, user-visible Markdown message before opening a decision form. Include the
facts and evidence the user needs for this choice. Keep the form prompt short and identify what it applies to
by round, revision or finding IDs. Use the user's language for both messages.

- For QA-plan approval, show the current plan, its round and revision, and the effective scope. Include
  recording choices and their scenario IDs. Resolve questions that change eligibility, expected behavior
  or execution before presenting the plan for approval.
- For a fix offer, show every finding covered by the offer, with its ID, cause, impact and evidence. For
  static or review findings, give the relevant file and line. For QA findings, give the scenario ID, minimal
  reproduction, expected and actual result, and the decisive observation or artifact link. Summarize the
  finding in the message itself so it can be understood without opening the report.
- For a prerequisite or scope decision, show the blocked stage, the reason, and how each choice affects
  the run. Defer optional questions unrelated to the pending approval.

After posting the context, invoke the native question tool exposed in the current conversation:

| Client | Tool |
| --- | --- |
| Cursor | `AskQuestion` |
| Claude Code | `AskUserQuestion` |
| Codex | `request_user_input` or `request_user_input_async` |

Codex exposes `request_user_input` only in Plan mode unless its default-mode feature is enabled, and
`request_user_input_async` only for models that support it. Without either, use the chat fallback below.

Ask one decision at a time. Use separate fields in one native form only for independent choices covered by
the same step, such as plan approval and optional recording consent. If a second question is needed, resolve
it in the appropriate step with the same native tool.

If the tool is unavailable in this session or cannot display the question, ask the same focused question
with the same options in chat and wait. A skipped or dismissed required decision stays pending until
the user answers explicitly.
