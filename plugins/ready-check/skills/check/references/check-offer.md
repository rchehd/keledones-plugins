Use this offer for completed tasks and natural-language requests for validation. Reuse the task, its changed
paths and behaviors, and the applicable profiles already known. If needed, inspect the scoped diff and
read-only profile discovery (`scripts/ready-check.py profiles --project <repo>`). A stack elsewhere in the
repository does not determine checks for this task. Do not run validation or install tools while making the offer.

Ask one question in the user's language. Always display each applicable stage as a choice: static checks,
code and security review, and QA. Make all applicable checks, a custom combination and skip available.
Name the actual scope in short labels or descriptions. A yes/no question alone does not meet this offer.

- Claude Code: use `AskUserQuestion`. In a four-option multi-select, list **Static checks**, **Code and
  security review**, **QA**, and **Skip**. Say that selecting all applicable stages runs the full check
  and that Skip is a separate choice. If an answer combines Skip with checks, clarify before acting.
- Codex: use `request_user_input` or `request_user_input_async` when available. Cursor: use its native
  question tool. In a single-select UI with room, list **All applicable**, the individual stages, and
  **Skip**. Use free text for combinations or for choices beyond the UI's limit.
- If the UI cannot show each stage, show **All applicable**, **Choose checks**, and **Skip**. In
  **Choose checks**, list each applicable stage and accept any combination. With no question tool, list
  the same choices in chat and wait. Omit inapplicable stages in every client.

Use the task's outcomes to choose the QA options. A workflow-only change can offer CI QA for its jobs and
artifacts. A changed CLI flag can offer CLI QA, and an API-only change can offer API QA. A change to a web flow
and its API can offer both Playwright and API QA. Offer native mobile QA for affected device behavior.
If browser tests are the deliverable, name the project runner in the offer, such as "Run changed Cypress specs".
If only static analysis and review are evident, offer those without a runtime mode. If the scope is unclear,
offer all applicable checks, a custom selection and skip. Resolve consequential scope questions after consent.
An unqualified yes means all applicable checks. An explicit subset stays scoped. Get separate approval
for the QA plan when scenarios apply.
