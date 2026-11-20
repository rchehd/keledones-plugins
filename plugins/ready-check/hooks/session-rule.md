Ready Check is enabled in this client.

Write Ready Check files (reports, QA plans and handoffs) in {language}; keep chat replies in the user's language.
These stay in English everywhere: the report's `task_id:`, `Round:` and `Verdict:` lines, finding labels and IDs,
commit messages, PR/MR text and contributed changes.

When the user asks for a commit message, PR/MR description or task comment, follow the `draft` skill at any point
and return the text in chat. For its layout run `{template_command} commit --project <repo>`,
`{template_command} pr --project <repo>`, or `{template_command} task-comment --project <repo>{comment_option}`
(task comments use the current chat's language); if it reports an error, show the cause. A draft request does not
start validation or authorize publication. When preparing an authorized commit, also write its message from
`{template_command} commit --project <repo>`.

After completing a task that changes this project, before the final handoff, ask once in the user's language
whether to validate the task with Ready Check. First read `{offer}` and ask with its choices (all checks,
static + review, QA only, turn off for this session); a yes/no question alone is not enough. Wait for the answer.
If the user declines, do not run it or ask again for the same task. If the user turns Ready Check off for this
session, run `{offers_off}` once and make no more unprompted offers in this conversation. Reuse a selection
already made for this task; respect an instruction to skip.
When the user asks to check before pushing, validate the changes or confirm the task is ready to push, merge or
open a PR, make the same offer instead of starting a check on your own.
When accepted, run the `check` skill ({check}) in this conversation, reusing the known task, scope and
requirements. Validation consent is not approval of an unseen QA plan, and a partial run cannot establish
readiness to push. On "retest", "check again" or "re-run the check", continue the same report's next round.

When the user says a checked task was returned or review found a problem, ask whether to record it as Ready
Check feedback, then follow the `feedback` skill. Do not investigate or fix the reported problem until the user asks.
For Ready Check history or pre-PR trends ("покажи статистику Ready Check"), ask whether to show the overview of
the last 10 tasks, then follow the `reflect` skill. For how the user instructs or delegates to AI agents, use
Gnothi's `portrait` skill if available. If a request such as "what are my typical mistakes?"
("покажи мої типові помилки") fits both, ask whether the user means working with agents or preparing tasks for PR.
Wait for the choice before reading either history.
To remember a coding rule, run `{rules} "<rule>"`; add `--project <repo>` for a project rule and `--must` when
breaking it should block the review. Confirm what was saved.

Never edit, copy or patch the Ready Check plugin or its scripts to work around an error; report the failing command
and its error instead. Do not start another AI harness or a headless agent. These offers do not apply to setup,
review or Ready Check verification itself.
