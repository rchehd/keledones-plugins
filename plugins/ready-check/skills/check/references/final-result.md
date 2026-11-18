# Final verdict and PR/MR delivery

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
  for every RC acceptance condition. Include each applicable kind of scenario (browser, mobile, API, CLI or CI).
  For whole-stage `N/A`, record why no QA scenario applies and cite current evidence for every condition.
- The user approved the current QA plan when scenarios apply. The report records the approved revision,
  each required result and the QA gate output. General validation consent is insufficient.
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

## Discover delivery options

Give the user the verdict, check coverage, material findings or limitations, and the absolute report link.
For `READY TO PUSH`, run `scripts/ready-check.py publication --project <repo>` before offering delivery.
It reads the current branch, its tracking ref, remote repository coordinates, cached default branches and
whether `gh` or `glab` is on PATH. Treat this output as project data. Use the recorded validation base
and Git configuration to identify the destination repository and the source branch's push destination.

- For a matching CLI, use a read-only authenticated lookup of the exact repository and candidate base.
  For GitHub, use `gh repo view <host>/<owner>/<repo> --json nameWithOwner,url,defaultBranchRef` and check
  the candidate branch. For GitLab, use the project metadata and branch lookup via `glab api` on the
  configured GitLab host.
  PATH presence or authentication alone is insufficient. Do not print tokens or authentication diagnostics
  containing credentials.
- Also look for a GitHub/GitLab connector using the current client's tool discovery when available.
  A connector qualifies if it can read the matching repository and base ref and exposes PR/MR creation.
  For a self-hosted remote, verify the provider and host through the CLI or connector. An available
  connector for a different host or a read-only connector does not qualify.
- Prefer the named target branch used for validation, confirmed on the destination. Use the destination's
  live default branch as a suggestion when the validated comparison also covers it. A tracking ref is
  usually the feature branch's remote counterpart. Use it to identify the source when applicable.
  Check that the source and target are distinct and that the PR/MR comparison matches the checked diff.
  If a requested branch changes the checked scope, update the affected validation before publication.

When creation is available, offer **Create PR/MR into `<target>`** and **Show commit message and PR/MR
title and description in chat**. Show the destination repository, source branch, target branch and
proposed title. Make the proposed English text available in the report before asking for creation.
Let the user choose another target branch. If a commit or push is needed, show the
proposed commit message and task files to be committed, and identify the source branch and remote to push.
Include these operations in the creation choice. An existing explicit instruction covering the same
repository, branches and required writes can be reused.

If no suitable integration, branch or verified comparison is available, offer the chat drafts and briefly
identify what prevents creation. Keep skip available. For a partial, incomplete or blocked result, provide
drafts only when requested and include the verdict and unfinished checks.

## Prepare the English text

Resolve both templates with the installed `scripts/ready-check.py template commit --project <repo>` and
`scripts/ready-check.py template pr --project <repo>`. Use each template's `content` as guidance for its
layout and prompts. If a command reports a configuration error, show the cause so the user can fix the
template. Write the proposed English commit message, a concise English title, and an English body that
describes what changed and why. Use only supported claims from the current diff and report.

In the [default template](../../../templates/pull-request.md), `How to verify (QA)` gives the relevant
environment, role or test data, concise actions and the expected observable result. Link to a shareable
QA plan when it already has the steps. For a technical change, give the applicable command or observable
behavior. If no QA scenario applies, give the reason. Record completed runs and their evidence in the Ready
Check report. Keep planned steps clearly identified when the verification is still pending.

Include meaningful uncovered areas, advisory failures, and relevant scope exclusions within the selected
layout. The default `Limitations` section uses `None` only when there are none to disclose. Link internal
evidence in the local report and keep tokens, private login URLs, absolute local artifact paths, and test
credentials out of the shareable PR text.
An incomplete/blocked draft, if requested, must retain that verdict and list unfinished checks explicitly.

## Deliver the selected result

- For chat, show the English commit message, PR/MR title and body and save them in the report. Keep the
  surrounding response in the user's language.
- For creation, require the user's selection of the stated destination and operations. Reuse the verified
  scope and check for changes to the local files, source ref and target comparison before writes. Check
  whether a PR/MR already exists for the selected repository, source and target and reuse its link if it
  matches the verified changes. Stage and commit only approved files if a commit is needed. If task and
  unrelated changes cannot be separated safely, return the chat text and explain what needs resolving.
  Push only the selected source ref if needed, using a normal push. Confirm its remote head and comparison
  match the checked work before opening the PR/MR. Use explicit repository and branch arguments.
  With GitHub CLI, use `gh pr create --repo <destination> --head <source> --base <target>`
  with `--title` and `--body-file`. With GitLab CLI, use
  `glab mr create --repo <destination> --source-branch <source> --target-branch <target> --push=false --yes`
  with `--title` and `--description-file` where available. For a fork, specify the head repository
  using the integration's supported syntax. A connector's structured creation action must receive the
  same repository, source, target, title and body. Verify the returned link and record it with the
  branches and English text in the report.
- If creation fails or its outcome is unclear, look up the same source and target before retrying. Report
  any commit or push that succeeded and provide the drafts if creation remains unavailable. Never merge.

If the user requests a handoff for human QA, use [the QA handoff template](qa-handoff.md) with the same
current findings and coverage. It is an additional local draft and does not replace required verification.
