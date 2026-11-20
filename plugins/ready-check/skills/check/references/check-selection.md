# Check selection

Record the selected stages before running checks. Use the [scope-specific offer](check-offer.md) and
reuse an explicit choice already in the conversation. An unqualified `check` request or a plain yes
to the offer means `full`. A later instruction to narrow or expand the selection updates the report.

| Choice | Stages |
| --- | --- |
| All / `full` | `static`, `review` (requirements, framework/stack practices and security), `qa` |
| Lints / statics | `static` |
| Code review / security | `review`, including version-aware framework/stack practices and security from the applicable profiles |
| Behavioral QA | `qa` for applicable browser, mobile, desktop, API, CLI and CI outcomes, with an approved scenario plan |

Accept explicit combinations. Selecting every applicable stage with all applicable coverage is full validation;
a stage that does not apply is `N/A` with a reason, not `NOT_SELECTED`.
When the user names only a QA kind, such as Playwright QA, record the requested scope and leave other
applicable QA kinds outside the verdict. Such an exclusion makes the result partial.
Never silently narrow a failing full
run to obtain success. Preserve known findings and explain scope changes if the user explicitly narrows it.
Execute selected stages in static → review → QA order. A selected earlier
stage's failure or incompleteness blocks later selected stages. Mark unselected stages `NOT_SELECTED`,
never PASS or N/A. They are not waived full-workflow gates. A standalone review or QA is a deliberately
partial assessment and does not require installing or running unselected linters.

## Partial scope and freshness

In a partial run without statics, record read-only scope evidence for each applicable profile and application
pair: application, profile/version, actual framework version, HEAD, base, merge base, runner/config,
mode (`--base` or `--commits` with SHAs), changed paths, complete tracked diff including staged/unstaged changes and content hashes of new
non-ignored files. Use Git and standard-library hashing, saving evidence in the reports directory.
Record unavailable facts explicitly; missing essential source/runtime correspondence makes that selected
stage INCOMPLETE. Do not treat this source identity as a successful static result.

Compare this evidence before and after each selected stage and on resume. Code/scope/config changes
invalidate dependent results. When statics are selected, use their normal doctor/snapshot identity instead.
Unavailable unselected static tools alone do not block standalone QA or code review. Missing tools actually
needed by a selected verification still do. QA also checks current running code/assets/config/data.

## Result boundaries

Use `BLOCKED` for a confirmed blocker and `INCOMPLETE` for missing required evidence in the selected scope.
When selected partial stages complete successfully, use `PARTIAL CHECK COMPLETE`, list exactly what passed,
and list all unselected stages and remaining limitations. Never say READY TO PUSH, fully validated, or
all checks pass for a partial selection. A whole-stage justified N/A counts as assessed only for its stated scope.

Only full scope with all current gates, review dimensions, approved QA coverage (or reasoned whole-stage
N/A), and no unresolved required question can produce READY TO PUSH. After a successful partial run, offer
the [remaining checks or delivery](final-result.md#continue-a-successful-partial-run). PR/MR text and
drafts retain the partial verdict and unperformed checks.

If the user selects more checks, update the selection in the same report. Run only the chosen remaining
stages and keep other stages `NOT_SELECTED`. Carry completed results forward only if the diff, requirements,
profile, runner and relevant runtime still match. When newly selected statics precede carried review or QA,
verify equivalent scope and require the current static gate to pass before relying on those results.
If earlier results are stale or lack equivalent evidence, explain why and get a decision before rerunning them.
Selecting a previously omitted QA scope still requires plan approval. Combine all current results for the
next verdict using the full-workflow gates when the selection now covers all applicable checks.
