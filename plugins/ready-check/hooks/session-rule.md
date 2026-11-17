Ready Check is enabled in this client.

Write Ready Check files (reports, QA plans and handoffs) in {language}; keep chat replies in the user's language.
These stay in English everywhere: the report's `task_id:`, `Round:` and `Verdict:` lines, finding labels and IDs,
PR drafts and contributed changes.

When drafting a commit message or preparing an authorized commit, run `{template_command} commit --project <repo>`.
For a project PR description, run `{template_command} pr --project <repo>`.
Use the selected content as layout and prompts for the draft. If it reports an error, show the cause.

After completing a task that changes this project, before the final handoff, ask once in the user's
language whether to validate the task with Ready Check. Offer all checks, static/lint checks,
code review and security, QA (browser with Playwright, mobile, API, CLI or CI), a combination, or none.
Wait for the answer. If the user declines, finish without running it or asking again for the same task.
If validation and its check selection were already requested or accepted for this task, reuse them.
An unqualified request for Ready Check or an affirmative answer without a narrower selection means all checks.
Respect any explicit instruction to skip validation.

When the user asks to check before pushing, validate the task or changes, or confirm it is ready to push, merge
or open a PR (for example "check before push", "pre-push check", "validate this", "validate my changes",
"is it ready to push?"), do not start a check on your own: ask once whether to run the Ready Check check and
which checks, then follow the answer.

When accepted, run the installed Ready Check `check` skill ({check}) in the current conversation and follow it.
Reuse the task requirements, application and diff scope already known; clarify missing requirements or
consequential ambiguities with the user. Validation consent alone is not approval of an unseen QA plan.
A partial run reports only its checked scope; it cannot establish that the task is ready to push.
When the user asks to retest after a fix ("retest", "check again", "re-run the check"), continue the same Ready
Check report with its next round through the `check` skill.
When the user says a checked task was returned or review found a problem ("the task was returned", "lead sent it
back", "review found a bug", "QA returned the task", "record feedback"), ask whether to record it as Ready Check
feedback, then follow the `feedback` skill. Do not investigate or fix the reported problem until the user asks.
When the user asks about their Ready Check history ("show my Ready Check stats", "how did my recent tasks go",
"what are my typical mistakes", "reflect on recent tasks", "analyze my last tasks"), ask whether to show the Ready
Check overview of the last 10 tasks, then follow the `reflect` skill.
When the user asks to remember a coding rule for Ready Check (for example "always prefer switch over if"),
save it with `{rules} "<rule>"`; add `--project <repo>` for a project rule (stored in the git-excluded
`ai/ready-check/`; the team shares it with `git add -f`) and `--must` when breaking it should block the review.
Confirm what was saved.
Never edit, copy or patch the Ready Check plugin or its scripts to work around an error; report the failing command
and its error instead.
Do not start another AI harness or a headless agent. This offer does not apply to setup, review or
Ready Check verification itself; do not create a loop.
