---
name: feedback
description: Record that a task Ready Check checked was returned (or accepted) after human review, with the reason and whether Ready Check missed it, so reflect can learn from it. Use when the user says the task was returned, the lead sent it back, review found a bug, QA returned the task, or asks to record feedback; ask before recording when triggered by such a phrase.
---

# Record feedback

Respond in the user's language. Feedback only records a fact. While handling it, never investigate, reproduce,
run the application or a browser, search the web, write scripts or edit any file: what happened and whether Ready
Check missed it come from the user, not from your own testing. Investigating or fixing the problem is separate work
that starts only when the user chooses it in step 6.

1. When a phrase such as "the task was returned", "lead sent it back", "review found a bug", "QA returned the task" or
   "record feedback" triggered this skill rather than the explicit command, ask once: "Record this as Ready Check
   feedback?" Continue only after a yes.
2. Collect from the conversation, asking only for what is missing (one question, with options):
   - who returned it: lead, qa, client or other;
   - the reason in one sentence;
   - missed: ask the user; `yes` only when they confirm the problem was in the code version and scope Ready Check
     checked; `no` when it was a new requirement, a later commit or outside the checked scope; otherwise `unknown`;
   - area: the checklist section it belongs to (for example "I. Render output, templates and cache"), or a short word.
   A missing reason stays `unknown`; record the fact anyway.
3. Run `python3 <plugin>/scripts/ready-check.py feedback add --project <app> --returned yes --by <who> --reason
   "<reason>" --missed <yes|no|unknown> --area "<area>" --source chat` (`py -3` on Windows; the plugin root is two
   directories above this file's directory). Without `--task` the newest task on the branch is used.
4. Exit code 3 (`CHOOSE_TASK`) means no task was found: show the listed tasks, ask which one, and rerun with
   `--task <task_id>`; if the user does not know, rerun with `--task unknown`.
5. Confirm what was recorded in one line.
6. Then ask once what to do next, with options: look into the problem, fix it (ordinary work, then a new `check`
   round), or nothing. Stop until the user answers, and do only what they choose.

`feedback list --project <app>` shows recent records.
