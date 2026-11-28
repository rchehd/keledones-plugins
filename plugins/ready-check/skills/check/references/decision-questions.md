# Decisions during Ready Check

Show the facts and evidence the user needs for a choice before asking it. Keep the question short and
identify what it applies to by round, revision or finding IDs. Use the user's language for both.

- For QA-plan approval, show the current plan, its round and revision, and the effective scope. Include
  recording choices and their scenario IDs. Resolve questions that change eligibility, expected behavior
  or execution before presenting the plan for approval.
- For a fix offer, show every finding covered by the offer, with its ID, cause, impact and evidence. For
  static or review findings, give the relevant file and line. For QA findings, give the scenario ID, minimal
  reproduction, expected and actual result, and the decisive observation or artifact link. Summarize the
  finding in the message itself so it can be understood without opening the report.
- For a prerequisite or scope decision, show the blocked stage, the reason, and how each choice affects
  the run. Defer optional questions unrelated to the pending approval.

## Long context

QA-plan approval, and a fix offer whose findings do not fit in a few lines, have long context. Clients can
hide text written just before a question form: Claude Code dims or hides it while `AskUserQuestion` is open,
Cursor can drop the prose of a turn that calls `AskQuestion`, and Codex collapses messages written between
tool calls. Put long context where the form cannot cover it:

1. Save it as Markdown in the task directory, for example `qa-plan-round-<N>-rev-<R>.md` or
   `fix-offer-round-<N>.md`.
2. Show it and ask according to the client:

| Client | Show the context | Ask |
| --- | --- | --- |
| Claude Code with `SendUserFile` (desktop app, Remote Control) | Send the file with `display: render`; give a two-line summary in the message | `AskUserQuestion` |
| Claude Code without `SendUserFile` (terminal) | Post the full context as the turn's final message | In the same message; end the turn |
| Codex | Post the full context as the turn's final message | In the same message; end the turn |
| Cursor | Post the full context as the turn's final message | In the same message; end the turn |

In a chat question, list the options as a short numbered list and wait for the reply. Link the saved file
under the context.

## Short decisions

For a decision whose context fits in a few lines, post the context, then invoke the native question tool
exposed in the current conversation:

| Client | Tool |
| --- | --- |
| Cursor | `AskQuestion` |
| Claude Code | `AskUserQuestion` |
| Codex | `request_user_input` or `request_user_input_async` |

Codex exposes `request_user_input` only in Plan mode unless the `default_mode_request_user_input` feature is
enabled, and `request_user_input_async` only for models that support it. Cursor does not expose `AskQuestion`
to every model; for example, Auto can route to a model without it. Without the tool, ask in chat.

Ask one decision at a time. Use separate fields in one native form only for independent choices covered by
the same step, such as plan approval and optional recording consent. If a second question is needed, resolve
it in the appropriate step with the same method.

If the tool is unavailable in this session or cannot display the question, ask the same focused question
with the same options in chat and wait. A skipped or dismissed required decision stays pending until
the user answers explicitly.
