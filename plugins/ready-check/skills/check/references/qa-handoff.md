# Optional QA handoff draft

Use this only when a QA handoff is requested. Write in the Ready Check file language from the session context unless the user asks for another.
Draw from the same current Ready Check report; do not invent a ticket system's mandatory fields or claim
that any organization has approved this format. Keep authentication links, credentials, and private local paths out
of text intended for a ticket. Save locally for human review; do not send it.

```markdown
Task: <Requested outcome>
Verdict / checked version: <Current verdict, HEAD and scope>
Environment: <Shareable test-environment description>

Requirements:
- RC-001: <Acceptance condition and current result>

Verified:
- <Actual flow, role, expected/observed result, and suitable evidence reference>

Suggested human QA:
- <Relevant remaining exploratory case, clearly distinguished from completed checks>

Findings:
- <F-ID, severity/impact, blocker status, role/preconditions, safe reproduction steps,
  expected/actual result and evidence; or None>

Limitations and test data:
- <Untested areas, setup prerequisites, retained fixture IDs and cleanup scope>
```

A required unverified case keeps readiness `INCOMPLETE`; moving it to “Suggested human QA” cannot create
a ready verdict. Preserve known defects and their blocker status when preparing a handoff after failure.
