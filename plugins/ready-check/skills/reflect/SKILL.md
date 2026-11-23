---
name: reflect
description: >-
  Show recent Ready Check task outcomes, recurring review or QA gaps, and returns after human review.
  On request propose improvements to pre-PR review and QA checklists, rules or the plugin.
  Trigger on "show my Ready Check stats", "what should I improve before PRs?",
  "покажи статистику Ready Check", or "що покращити в підготовці задач до PR?".
---

# Reflect on recent tasks

Respond in the user's language. Counting is done by the script; you group free text and write proposals.
Resolve the plugin root two directories above this file's directory; Python is `python3` (`py -3` on Windows).

For an ambiguous request such as "what are my typical mistakes?" or "покажи мої типові помилки", ask whether the user means preparing
tasks for PR or working with AI agents. Use `reflect` for the former and offer Gnothi's `portrait` for the latter
if available. Wait for the choice before reading data. An explicit request for `reflect` selects the PR scope.

## 1. Overview (no proposals)

1. When a phrase triggered this skill rather than the explicit command, ask once: "Show the Ready Check overview of
   the last 10 tasks?" Ask how many tasks only if the user wants a different number.
2. Run `ready-check.py reflect-collect --project <app> --tasks <N> --html` for the digest and offline report.
3. Open the read-only overview with Ready Check's `show_view` tool using `view: reflect`, the repository path,
   `snapshot: <snapshot_id from the collector>` and `locale: uk` for Ukrainian or `en` otherwise.
   A host without MCP Apps returns a local
   browser URL for the same view. Give the URL if returned. If the tool is unavailable, run
   `ready-check.py ui serve --project <app> --view reflect --snapshot <snapshot_id> --locale <en|uk>` in the background and
   give its URL. The collector's saved HTML is also available if the local server cannot start.
   Show a short summary in chat, using this format when the user chooses text:

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
   When present, report interactive false-positive and risk-acceptance counts from `view_dispositions`.
   Use each task's `view_feedback` source and reason to identify noisy checks separately from task returns.
4. Give the offline HTML report path (`html` in the JSON). Its charts use the installed browser tools.

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
