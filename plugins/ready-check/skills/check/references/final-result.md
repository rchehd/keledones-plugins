# Final verdict and English PR draft

Use the same report and current scope as `check`. Read the actual diff, including new files, deletions,
and renames, to describe the delivered change. A task description, inferred implementation, or planned
scenario cannot stand in for completed work or verification.

## Verify readiness

Read [check selection](check-selection.md) first. A partial run ends with BLOCKED, INCOMPLETE or
PARTIAL CHECK COMPLETE for the selected scope. Compare current identity for each selected stage,
list NOT_SELECTED stages and stop short of overall readiness. Do not require unselected linters for
standalone QA/review. The full-readiness checks below apply only to full validation; an optional partial
PR draft must state unperformed checks and cannot describe the task as ready.

Compare the current task requirements revision and scope with the review and QA records. For every applicable
profile and application pair, compare snapshot, HEAD, merge base, application, profile/version, and runner
from a fresh packaged doctor with the saved static result. The immediately preceding QA-end doctor results can be reused if nothing changed
after it; otherwise run it again. Current prerequisites must be available. Doctor success does not replace
a static result, review conclusion, or runtime check.

Check the following before marking the task ready:

- The task, applicable profiles and roots, base and exclusions are resolved, and every current RC is `DEFINED`.
- Static checks have saved successful gates for all current snapshots, including every mandatory applicable
  result or explained `N/A`; review has a matching complete `PASS` matrix and no requirement gap.
- Review includes applicable framework/stack practices from every applicable profile for actual installed versions and security paths,
  with code evidence and no missing essential coverage or unresolved blocking finding.
- QA has a matching `PASS` or justified whole-stage `N/A` gate, environment evidence, and current coverage
  for every RC acceptance condition through scenarios or the necessary technical verification.
  For whole-stage `N/A`, record why no running browser environment is needed instead of inventing one.
- For applicable browser QA, the user approved the current requirements/scenario plan, with approved
  revision and scenario coverage recorded. General validation consent is insufficient. A justified whole-stage
  N/A needs its current technical evidence instead of approval of nonexistent browser scenarios.
- No current blocking finding or unresolved question remains. Proposed regressions are not silently promoted
  into requirements, and an explicit RC violation is not downgraded to a cosmetic advisory.
- Required work in the agreed task scope is covered. Changes outside the union of applicable profiles and roots are visible;
  if they belong to the task and remain unverified, they prevent readiness. Do not silently shrink scope.

If a gate or environment is stale, return to the earliest affected stage. Retain old observations as history
without claiming a current pass. After a code fix repeat statics, affected review, and failed/related QA.
Update TODO items from actual results rather than ticking them to make the report appear finished.

Use one overall verdict:

| Verdict | Meaning |
| --- | --- |
| `BLOCKED` | A confirmed current blocking static/review/QA finding remains, even if other coverage is incomplete |
| `INCOMPLETE` | No current confirmed blocker establishes failure, but a required answer, setup, evidence, scope, or check is missing/stale |
| `PARTIAL CHECK COMPLETE` | Selected partial checks succeeded; unselected stages remain unverified and task readiness is not established |
| `READY TO PUSH` | All required current gates and acceptance conditions are covered with no remaining blocker or required question |

Describe advisory findings and explicit scope limitations even on a ready result. These cannot excuse an
unverified acceptance condition or required check. Readiness applies to the recorded code and runtime state;
it does not include publication or an assurance about untested environments.

## Draft the PR in English

After the verdict, ask once in the user's language whether to prepare the PR title and description. Write them
only after a yes (or when the user already asked for them); on no, finish without a draft. Then produce a concise
title describing the resulting change and a summary explaining what changed and why, using the template below.
Use only supported claims from the current diff. In `Testing`, list checks and flows actually completed,
their outcomes, and relevant roles/environment. Distinguish successful code review from runtime proof.
Do not say “all tests pass” when checks were skipped, advisory checks failed, or only a subset ran.

In `Limitations`, include meaningful uncovered areas, advisory failures, and relevant scope exclusions;
use `None` only when there are none to disclose. Link internal evidence in the local report, keeping tokens,
private login URLs, absolute local artifact paths, and test credentials out of the shareable PR text.
An incomplete/blocked draft, if requested, must retain that verdict and list unfinished checks explicitly.

```markdown
PR title: <Concise English title>

## Summary
- <Delivered behavior and reason>

## Testing
- <Completed check or observed flow, result, and relevant context>

## Limitations
- <Material limitation, or None>
```

Give the user a compact final response: verdict and reason, check/coverage summary, important findings or
limitations, absolute report link, and the question about the PR title and description. When the user agrees,
show the English draft in the chat and save it in the report. Keep the surrounding
response in the user's language. A ready result may say the changes are ready to push; do not run Git write
commands, push, create a PR, or send a comment. This workflow produces a reviewable draft only.

If the user requests a handoff for human QA, use [the QA handoff template](qa-handoff.md) with the same
current findings and coverage. It is an additional local draft and does not replace required verification.
