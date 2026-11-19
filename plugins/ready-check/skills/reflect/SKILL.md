---
name: reflect
description: Show an overview of recent Ready Check tasks (rounds, defects, returns after human review, typical errors) as text and an HTML report with charts, and only on request propose improvements to the review and QA checklists, rules or the plugin. Use when the user asks for Ready Check stats, how recent tasks went, typical mistakes, or to reflect on or analyze recent tasks; ask first when triggered by such a phrase.
---

# Reflect on recent tasks

Respond in the user's language. Counting is done by the script; you group free text and write proposals.
Resolve the plugin root two directories above this file's directory; Python is `python3` (`py -3` on Windows).

## 1. Overview (no proposals)

1. When a phrase triggered this skill rather than the explicit command, ask once: "Show the Ready Check overview of
   the last 10 tasks?" Ask how many tasks only if the user wants a different number.
2. Run `ready-check.py reflect-collect --project <app> --tasks <N> --html`.
3. Show structured text, no charts in the chat:

   ```text
   Overview: <N> tasks, <first date>–<last date>

   Tasks
   - <task_id> (<date>) — <rounds> rounds, <verdict>, returned: <no | yes: reason>

   Totals
   - Passed in round 1: <x> of <tasks with summaries>
   - Confirmed defects: <tasks> (findings: <issue> issue, <suggestion> suggestion, …)
   - Returned after human review: <x>, missed by Ready Check: <y>
   - QA cases that failed because of the test: <z>

   Typical errors
   - <area> — <count> (in <tasks> tasks)
   ```

   Group feedback reasons by meaning into the typical errors; never change the script's counts. Say which values are
   `unknown` (older tasks without round summaries) instead of guessing.
4. Give the HTML report path (`html` in the JSON). Charts need the installed browser tools; otherwise it has tables.

## 2. Ask

Ask: "Propose improvements based on this history?" On no, stop here.

## 3. Proposals

Read report excerpts, evidence or the harness transcript only where the digest is not enough. Each numbered proposal
states: the case or pattern with evidence links, the type (implementation defect the review should catch, QA
scenario problem, Ready Check bug, process note), the exact item text, and the target (a `review` or `qa` checklist
section, a rule, or plugin code). Propose only with a clear cause or at least two occurrences. Write checklist items
and rules in English and in the checklist's style.

## 4. Decide

Ask in one message; the user may pick several options per item, or one choice for all:

```text
1. <short title>   [ ] project   [ ] global   [ ] PR to Ready Check   [ ] skip
2. …
```

A Ready Check bug offers only "PR / bug report" or "skip". Example answers: "1: project + PR, 2: global, 3: skip",
"all: project".

## 5. Apply

- project or global: follow the `customize` skill for each item (kind, section, scope from the decision).
- PR to Ready Check: follow the `contribute` skill with the proposal.

Finish with what changed and where, and remind the user to commit shared project files
(`git add -f .ai/ready-check/rules.md .ai/ready-check/extensions`).
