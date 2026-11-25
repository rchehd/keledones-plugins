Use this offer for completed tasks and natural-language requests for validation. Reuse the task, its changed
paths and behaviors, and the applicable profiles already known. If needed, inspect the scoped diff and
read-only profile discovery (`scripts/ready-check.py profiles --project <repo>`). A stack elsewhere in the
repository does not determine checks for this task. Do not run validation or install tools while making the offer.

Post the actual scope and use the [current client's question tool](decision-questions.md). Ask one question
in the user's language and name the scope in short labels or descriptions. A yes/no question alone does not
meet this offer.

- Claude Code: use a single-select `AskUserQuestion` with four options: **All checks** (static, review and
  QA), **Static + review**, **QA only** and **Turn off for this session**. The question UI adds its own Other
  (free text) and Skip; say that Other takes anything else, such as "static only" or "review only".
- Codex: use `request_user_input` or `request_user_input_async` when exposed (Plan mode only for the former unless
  the default-mode feature is enabled). Cursor: use its native
  question tool. List **All checks**, **Static + review**, **Static only**, **Review only**, **QA only**,
  **Skip** and **Turn off for this session**; take other combinations as free text.
- With no question tool, list the Codex choices in chat and wait.

When QA does not apply, drop **All checks** and **QA only**; in Claude Code show **Static + review**,
**Static only**, **Review only** and **Turn off for this session**. **Static + review** is then the full run:
record QA as `N/A` with the reason, not `NOT_SELECTED`. Omit any other inapplicable stage too.
**Skip**, "not now" or dismissing the question declines this task only. **Turn off for this session** means no
more Ready Check offers in this conversation, even after an end-of-turn reminder; run the `offers off` command
from the session context once so the reminder stops. A check the user asks for still runs.

Use the task's outcomes to choose the QA options. A workflow-only change can offer CI QA for its jobs and
artifacts. A changed CLI flag can offer CLI QA, and an API-only change can offer API QA. A change to a web flow
and its API can offer both Playwright and API QA. Offer native mobile QA for affected device behavior.
If browser tests are the deliverable, name the project runner in the offer, such as "Run changed Cypress specs".
If only static analysis and review are evident, offer those without a runtime mode. If the scope is unclear,
offer the same choices. Resolve consequential scope questions after consent.
An unqualified yes means all applicable checks. An explicit subset stays scoped. Get separate approval
for the QA plan when scenarios apply.
