Use this offer for completed tasks and natural-language requests for validation. Reuse the task, its changed
paths and behaviors, and the applicable profiles already known. If needed, inspect the scoped diff and
read-only profile discovery (`scripts/ready-check.py profiles --project <repo>`). A stack elsewhere in the
repository does not determine checks for this task. Do not run validation or install tools while making the offer.

Ask one question in the user's language. Offer all applicable checks, focused static/lint or review/security
options when relevant, QA options for the behavior that changed, and a way to skip. Name the actual scope
in short labels or descriptions. Accept a custom combination. Use the client's choice UI when available;
otherwise present the choices in chat. If the UI limits choices, group the focused options and explain how
to pick a subset.

Use the task's outcomes to choose the QA options. A workflow-only change can offer CI QA for its jobs and
artifacts. A changed CLI flag can offer CLI QA, and an API-only change can offer API QA. A change to a web flow
and its API can offer both Playwright and API QA. Offer native mobile QA for affected device behavior.
If browser tests are the deliverable, name the project runner in the offer, such as "Run changed Cypress specs".
If only static analysis and review are evident, offer those without a runtime mode. If the scope is unclear,
offer all applicable checks, a custom selection and skip. Resolve consequential scope questions after consent.
An unqualified yes means all applicable checks. An explicit subset stays scoped. Get separate approval
for the QA plan when scenarios apply.
