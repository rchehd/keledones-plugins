# Ready Check report template

Write the report in the Ready Check file language from the session context (English unless the user chose another),
with the PR draft in English. Replace bracketed fields with known facts or an explicit unknown;
keep unresolved preparation items open. Maintain the same report as answers arrive.

```markdown
# Ready Check

task_id: [Slug of the task title plus the date of the first run, from the reports command]
Round: [1 for the first run; increment after each fix or retest]
Verdict: [INCOMPLETE, BLOCKED, PARTIAL CHECK COMPLETE, or READY TO PUSH only for a full successful run]

<!-- The three lines above stay in English; the rest of the report uses the Ready Check file language. -->

Reason: [Open questions, confirmed findings, missing prerequisites, or current verified coverage]
Report: [Absolute report path]

## Task

[Requested outcome and source; state explicitly when the task is unknown]
Requirements revision: [Increment when criteria or exclusions change]

## Scope

- Check selection: [full, or selected static/review/qa combination and source of the user's choice]
- Unselected stages: [NOT_SELECTED with names; never implied PASS]
- Repository root: [Path or unresolved]
- HEAD: [Commit or unavailable]
- Mode: [`--base <ref>` or `--commits` with the task SHAs]
- Base ref: [Ref, or n/a in commits mode]
- Merge base: [Commit or unavailable]
- Changed files: [Paths, including new files, deletions and renames]
- Outside scope: [Uncovered changes, `uncommitted_outside_task`, or explicit exclusions]

| Profile / version | Application root | Runner | Detection or config evidence | Affected paths / exclusion reason |
| --- | --- | --- | --- | --- |
| [ID and version] | [Repository-relative path] | [Configured and effective if different] | [Markers or config] | [Paths, shared dependencies, or reason excluded] |

## Static checks

Stage status: [NOT_SELECTED, NOT_RUN, PASS, FAIL, INCOMPLETE, or N/A]

| Profile / application | Status | Snapshot or partial source identity | Doctor / static JSON | Checks, findings and prerequisites |
| --- | --- | --- | --- | --- |
| [One row per applicable pair] | [Status and reason] | [Current snapshot or Git/diff/untracked and config identity] | [Evidence paths] | [Results, linked finding IDs, and missing tools] |

For a report created before profile lists were introduced, use its existing profile, application and snapshot
as one row. If the applicable pairs change, refresh the affected evidence in the next round.

## Task requirements

| ID | Requirement | Source | Actor / condition / action | Acceptance condition | Verification method | Clarity |
| --- | --- | --- | --- | --- | --- | --- |
| RC-001 | [Requested behavior] | [Task text or human answer] | [Concrete context and trigger] | [Observable outcome] | [Planned check] | DRAFT or DEFINED |

## Proposed regression checks

[Checks suggested by the diff; keep separate from accepted requirements]

## Requirements review

Stage status: [NOT_SELECTED, NOT_RUN, PASS, FAIL, or INCOMPLETE]
Can proceed to selected QA: [false until selected preceding gates are current and successful]
Reviewed static snapshots: [Identity by profile/application or not yet reviewed]
Reviewed requirements revision: [Revision or not yet reviewed]
Current scope evidence: [Fresh doctor JSON when statics selected, otherwise partial source evidence]

| RC | Review status | Code evidence | Gap or uncertainty | Planned QA / technical verification |
| --- | --- | --- | --- | --- |
| RC-001 | IMPLEMENTED / PARTIAL / MISSING / NEEDS_CLARIFICATION / QA_REQUIRED | [Current file and line or explained absence] | [Specific result] | [Concrete scenario and expected outcome] |

### Framework/stack practices and security

Versions: [Exact framework, runtime and affected components/libraries; lock/installed/runtime sources and discrepancies]

Size: [Counted changed lines, generated files skimmed, and parts reviewed when above ~400 lines]
Change types: [Types from profile guidance and shared checklists, with the paths that triggered them]

| Profile / application | Section / item | Version / official reference | Code evidence | Result | Finding / reason |
| --- | --- | --- | --- | --- | --- |
| [Profile ID and root, or shared guidance and affected roots] | [Checklist item] | [Applicable version/source] | [File and line] | CHECKED / FINDING / INCOMPLETE / N/A | [Specific result or N/A reason] |

Not triggered: [Section — reason, for example "I. Render and cache — no render output or templates changed"]

Code quality and tests: [Each item of the code-quality checklist and, when applicable, the tests checklist, with
evidence and CHECKED / FINDING / N/A; or "Tests: N/A — no tests in the change or project for this code"]

| Coding rule (source) | MUST | Code evidence | Result |
| --- | --- | --- | --- |
| [Rule text (client settings / user / team)] | yes / no | [File and line] | CHECKED / FINDING / N/A |

### Findings

[Label each finding: issue (blocking) / suggestion / nitpick / question. For each finding: ID, RC IDs or regression label, blocking/nonblocking, trigger, expected/code-inferred
actual behavior, exact file and line, causal explanation, and regression/pre-existing/unknown attribution]

Done well: [One specific line, or omit]

### Review notes and limitations

[Nonblocking observations, inaccessible evidence, uncovered changes, applicable framework areas, and
reasons relevant checks did not apply. Keep code inspection separate from runtime verification.]

## QA

Stage status: [NOT_SELECTED, NOT_RUN, PASS, FAIL, INCOMPLETE, or justified whole-stage N/A]
Can proceed to final result: [false until current QA coverage is complete and no blockers remain]
Checked static snapshots and requirements revision: [Identity by profile/application or not yet checked]
QA plan revision: [Increment when scenarios, criteria, roles or data scope change]
Plan approval: [PENDING / APPROVED / REJECTED; human response and approved revision/RC revision/scenario IDs; not needed for justified whole-stage N/A or NOT_SELECTED]
Task type and source: [Feature acceptance or bug trigger/corrected expectation/regressions, from session/task/human]
Time: [Execution start/end or not run]
Environment: [Local URL, application/site mapping evidence, code/assets/config/data preparation, and identity]
Browser mode: [Requested and actual: visible (MCP) or background (CLI); browser/version, viewport, GUI limitations, approved fallback]
Risk map: [Changed areas with likelihood × impact (H/M/L) and the change types they come from]
Role sessions: [Actual test roles/accounts and isolation; no credentials or authentication links]
Browser readiness: [Actual launch/navigation evidence, missing dependency, or reasoned N/A]
Scope evidence: [Before/after doctor JSON paths and runtime correspondence checks]

| Scenario | RC / regression | Required, risk | Technique | Oracle | Depends on | Role and preconditions | Steps | Expected | Actual | Status (round) | Evidence / time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QA-001 | RC-001 | [Required/optional, H/M/L and why] | [Boundary values, state transition…] | [RC expected result or HICCUPPS item] | [Profile/root pairs and files/components] | [Context] | [Exact safe steps] | [Observable outcome] | [Observed outcome or not run] | PASS (round 1) / FAIL / INCOMPLETE / NOT_RUN / N/A | [Screenshot/snapshot, console/network/state proof, and time] |

### Exploratory session

Charter: [Explore <area> with <roles/data> to discover <risk>; action budget]
Covered: [What was varied, along SFDPOT where relevant]
Bugs / issues / questions: [F IDs, observations, open questions, or None]

### Accessibility

axe: [Pages/components scanned, rule set, violations with impact and whether the element is part of the change]
Manual: [Keyboard access, focus order and visibility, labels, readable errors]
Limits: [Automated rules cover only part of WCAG; what was not checked]

### RC verification coverage

| RC | Acceptance conditions | Scenario / technical evidence | Result / remaining gap |
| --- | --- | --- | --- |
| RC-001 | [All conditions] | [Executed scenario IDs or current technical check evidence] | [Verified, failure, or incomplete condition] |

### QA findings

[Continue report-wide F IDs: affected RCs/regression, oracle, severity/impact, blocking status and reason, actor and
preconditions, safe reproduction steps, expected/observed behavior, evidence, reproduction limits, attribution,
and likely code cause only if inspected. Keep questions, pre-existing issues, and suggestions distinct.]

### QA limitations and test data

[Untested roles/flows/environments and reasons, technical replacements for browser-inapplicable criteria,
created/modified data IDs, remaining cleanup and its agreed scope, session cleanup, or None.]

## TODO

- [ ] Establish the task and resolve requirement ambiguities.
- [ ] Resolve the application roots, diff scope, and applicable profiles.
- [ ] Run static checks.
- [ ] Review RC implementation, version-aware framework/stack practices and security using the applicable profiles.
- [ ] Show QA requirements/scenarios and obtain explicit approval of the current plan.
- [ ] Run applicable QA scenarios.
- [ ] Produce the verdict and ask whether to prepare the English PR title and description.

[Persisted copy of the harness task list; keep it in sync. Keep unselected stages NOT_SELECTED; do not tick
them as completed. Partial runs end with a scoped verdict; the English PR draft is written only after the user agrees.]

## Open questions

[Question, affected criteria or step, and what the answer changes; or None]

## Decisions

[Human answers and the criteria or scope they clarify; fix offers with the chosen side, approved finding IDs,
and files the agent changed]

## Verification

- Doctor: [NOT_RUN, or prerequisite status and JSON path; not proof that code passed]
- Static checks: [NOT_RUN, or status, JSON path, per-check findings/reasons, and log evidence]
- Requirements review: [NOT_RUN, or stage status, findings and matrix coverage]
- QA: [NOT_RUN, or stage result, coverage and evidence; reason if N/A]
- PR title and description: [NOT_REQUESTED, DECLINED or DRAFTED; a draft is not published]

## PR draft (English)

PR title: [Supported concise title, or NOT_RUN]

### Summary

[Actual delivered changes and reason, or NOT_RUN]

### Testing

[Only completed checks/flows and their results, or NOT_RUN]

### Limitations

[Meaningful uncovered areas/advisories, or None; exclude private authentication data and local paths]

## Next step

[Resolve a question, fix a finding and rerun affected stages, perform QA, or review the completed PR draft]
```
