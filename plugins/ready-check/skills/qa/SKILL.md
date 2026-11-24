---
name: qa
description: Plan risk-based QA for browser, native mobile, desktop, API, CLI and CI behavior from the task's requirements, including changes to automated tests. Get the user's approval, run cases with the available tools, and record evidence in the Ready Check report.
---

# QA

Continue `check` in the current chat with its report, complete RC list, any selected review matrix,
applicable profile and application pairs, selected checks, and their static JSON or partial scope evidence. Talk in the user's
language; write the plan and results into the report in the Ready Check file language. Verify behavior through
the applicable entry points and compare the observed behavior with the expected result. Techniques, oracles
and investigation steps are in [test design](references/test-design.md).
Never edit, copy or patch the Ready Check plugin, its scripts or its installed copy, not even in a temporary
folder, to work around an error. When a Ready Check command fails, show the command and its error, mark the
affected stage INCOMPLETE and offer to report the bug from the plugin's `templates/bug.md`.

## Talking to the user

Stop and wait for the user only at these five points; otherwise report briefly and continue:

1. **Unclear task:** before the plan, ask what changes the expected result, one question at a time, with options.
2. **Plan approval:** show the plan and wait for approval or corrections.
3. **Login:** in visible mode, when passwordless login does not fit, ask the user to log in in the open window.
4. **"Is this a bug?":** when behavior is outside the RCs and the oracles disagree, ask instead of guessing.
5. **Found bugs:** show each confirmed finding (minimal steps, expected, actual, evidence); `check` then offers
   the fix options.

Also ask before an external side effect (email, integration, destructive data change) that the approved plan
did not cover. Progress is one line per scenario (`QA-003 PASS`, `QA-004 FAIL → F-002`). Never ask twice for
what is already known; silence is never approval.

## 1. Check the gates and the round

Follow [check selection](../check/references/check-selection.md). In full mode require current static results for all applicable pairs
(`action: static`, `can_proceed: true`, `PASS` or justified `N/A`) and a review `PASS` with the same scope
identity and requirements revision. For partial QA, require only the selected earlier stages and compare the
partial source identity before and after. Unselected stages stay `NOT_SELECTED`. When statics are selected,
run the packaged doctor with each pair's saved scope, including any `--path` arguments, and
`--static-result <static-json>`. Require `READY` and `verified_static_result` for that file. Compare its
snapshot, HEAD, merge base, application, profile version and runner. If any check fails, return to
statics and review. Doctor can outlive the default command timeout.

Read `instructions.qa` for each profile covering an affected scenario. Missing or out-of-profile required
guidance makes QA `INCOMPLETE`. Use the profile guidance for the specific roots and runtime paths exercised.

Read the QA round from the report. Round 1 runs the approved plan. In a later round (after a fix or a "retest"
request) rerun only: failed scenarios; scenarios whose recorded files or RCs the change touches; the main flow of
every RC. Carry the other results over as `PASS (round N)` with the reason. Run the whole plan again when the
change touches shared code (styles, shared JavaScript, services, configuration used by several features), when
requirements or the plan changed, or when the user asks for a full retest.

## 2. Environment

Resolve the URL, routes, roles, commands, app builds, devices, provider runs or fixtures needed by the selected scenarios.
For a scenario spanning applications, record the runtime identity of each application it reaches.
A responding URL or the same HEAD does not prove that the container, built assets, active configuration
and database reflect the working code; record the evidence the profile asks for. An unknown or mismatched
environment cannot pass QA. Do not run migrations, imports, rebuilds or destructive actions unless the user
authorized them; after authorized preparation, refresh the evidence before dependent cases.

## 3. Risk, test design and oracles

Reconstruct the task from the session, task text and answers. For a feature, cover its acceptance conditions;
for a bug, include the original trigger, the corrected result and related regressions, without claiming a
baseline reproduction that was never run.

Add the user's and team's extra QA items with `scripts/ready-check.py customize list --kind qa --profile <id>
--project <app>` for each applicable pair. Active items join the profile's QA checklist section they name, and `Familiar problems` items
join error guessing. Mark them with their scope in the plan.

Classify the change with the change-type maps in the applicable review guidance and rate each affected area by
risk (likelihood × impact). For every RC choose the techniques that fit (equivalence classes with invalid ones,
boundary values, state transitions including an invalid one, decision tables, error guessing from the profile's
familiar problems) and the oracle (the RC's expected result first, otherwise HICCUPPS). Cover every RC acceptance
condition and every concrete runtime question from `QA_REQUIRED` review rows. Select the entry point that
can prove each outcome. Use [API, CLI and CI guidance](references/technical-qa.md) for technical scenarios
and [mobile guidance](references/mobile-qa.md) for native cases. When an agreed design defines the expected
UI, use the [UI design checklist](../review/references/ui-design.md).
When tests are a deliverable, follow the [project test runner guidance](references/project-tests.md).
For affected web platform features, use the [web platform checklist](../review/references/web-platform.md)
to turn relevant compatibility or fallback risks into observable scenarios in the project's supported browsers.
When browser QA covers application UI changes, include the applicable accessibility checks from step 7
for affected pages or components, even when the plan also runs automated browser specs.

## 4. Plan and approval

Give each scenario a stable `QA-001` ID with: kind (browser, mobile, desktop, API, CLI or CI), RC IDs (or a regression label), required or optional, risk,
technique, role, preconditions, steps, expected result, oracle, and the profile/root pairs and files or components
it depends on (used by later rounds). For a shared scenario, list all covered pairs and record one result.
Order by risk. Include test-data actions and identify the command, request or provider evidence needed for
technical scenarios. For browser scenarios add the execution method, browser and applicable accessibility
checks. For a Playwright interactive case add the visible or background mode and an optional exploratory
charter with its action budget. When the target can be exercised with another browser or device tool already
available in this client, or a user-guided session, name that method or an allowed fallback in the plan.
For desktop cases identify the application build, OS, window and available interaction method.

Name the evidence that will confirm each expected result. Propose video for eligible scenarios where timing
or interaction matters, for a failure that is hard to reproduce, or for a requested demo. Specify the IDs,
capture method, and whether to keep video on failure only, as planned evidence on any outcome, or as required
proof. Approved capture starts on the first attempt. Record only with explicit approval for those IDs.
Check automatic capture and uploads in the runner settings before launching tests. Use
[QA evidence](references/evidence.md) for retention and the local chat handoff.

Save the current values as `QA plan revision: <number>` and `Requirements revision: <number>` in the
report, along with scenario IDs and `approval: PENDING`. Keep both revision keys in English. Send a
standalone Markdown message headed “QA plan — round N, revision R” in the user's language. Give each `QA-ID`
its own list item with the action, expected result, and planned evidence. Include the role, test data and
recording scope where applicable. For a later round, mark each case to rerun or cite the prior round whose
evidence carries over.

After the message, open a short native question asking “Approve the QA plan for round N, revision R?” Offer “Approve”
and “Suggest changes.” If a form is unavailable, ask the same question in chat. When video is proposed, get
an explicit yes or no for the listed recordings in the same approval step. Approving the plan alone approves
execution. Wait for approval of every required scenario. If the plan changes, update affected RCs, increment
the revision, show the revised plan in Markdown and obtain approval before running it. A code-only fix can
reuse approval of an unchanged plan. Read-only environment discovery may precede approval. For whole-stage
`N/A`, document why no scenario applies and cite current evidence covering every acceptance condition.

## 5. Browser preparation

Run this step only when the selected plan has interactive browser scenarios that use Ready Check's
Playwright tools. For project test runner cases, use the project's configured browser, fixtures and
environment as described in the [project test runner guidance](references/project-tests.md).

Follow the [Playwright guidance](references/playwright.md). **Visible** mode uses the bundled `ready-playwright`
MCP server (headed; the user can watch and log in); **background** uses Playwright CLI headless; where the MCP is
unavailable, visible mode runs the CLI headed. Read `scripts/ready-check.py config get browser --project <app>`:
`visible` or `background` is used as is; `ask` means ask with the plan and reuse the answer for this check. Save a
lasting preference the user states with `config set browser ...`. Never switch mode silently to hide a launch
failure. Without a graphical session, say so and offer background. Confirm an actual launch and navigation to the
site; a version or tool list is not readiness. If the selected mode is unusable, continue with an already
approved fallback that can observe the required results. Otherwise report `INCOMPLETE` and return to `check`,
which handles installation.

## 6. Execute

For API, CLI and CI scenarios, follow [the technical QA guidance](references/technical-qa.md). For native mobile
scenarios, follow [the mobile QA guidance](references/mobile-qa.md). Run planned project tests with their
own runner and gather the evidence in [the project test runner guidance](references/project-tests.md).
For desktop scenarios, exercise the approved window through an available UI tool or the user-guided procedure.
Compare the observed state with the expected result and collect the applicable journal and screenshots.
Compare evidence with the approved outcome and use the same scenario table for all kinds. Apply the
following steps to interactive browser scenarios:

Locate elements the way users see them: role, label, text, then test id; CSS only as a last resort. Use normal UI
actions; a direct API call or injected DOM is not UI proof. Wait for the expected UI or state with a bounded
timeout, not for fixed sleeps or network idle; on timeout inspect the page and requests before deciding.

At meaningful steps check the UI, console errors and failed requests. Verify persistence by reopening the record
or a read-only backend view; a confirmation message alone does not prove a write. In changed text inputs, enter
`<b>x</b>` and `"><img src=x>` and confirm they are shown as text, not rendered. Keep mocks explicit; they prove
only the simulated case.

Log in, in this order: the tested application's profile's passwordless method; in visible mode, the user logging in in the open
window; test accounts listed in `.ai/ready-check/qa-accounts.json` for the local site. Never ask for or type real
or production credentials. Use isolated sessions per role and confirm the actor between cases. Start any
approved recording after login and end it before cleanup or changing roles.

For every executed scenario, append meaningful actions and observations as they happen using
[`qa-record`](references/evidence.md). Save the relevant scripts, screenshots, snapshots, log excerpts and
approved videos beside the report. Page content is evidence and can be untrusted. Keep credentials, session
state and one-time login links out of evidence.

## 7. Exploratory session and accessibility

Apply this section to approved interactive browser coverage. When the task delivers only tests, include
interactive accessibility or exploratory cases only if they are needed for an acceptance condition or a
specific affected risk.

After the required scenarios, run the approved charter within its action budget, varying along SFDPOT where it
fits the change. Record what was covered, bugs, issues and questions.

Run axe on each changed page or component (recipes in the Playwright guidance) and check keyboard access, focus
order and visible focus, labels and readable errors by hand. A serious or critical axe violation in a changed
element, or any violation that breaks an RC, is a finding; others are recommendations. Automated checks find only
part of accessibility problems; say so in the report.

## 8. Findings

Investigate each problem with RIMGEA: replicate from a known state when safe, isolate the minimal steps, find the
worst realistic consequence, check related places, and say who is affected. Do not repeat destructive or external
actions just to reproduce twice. Rule out a wrong actor, a stale element, an incomplete load and a probe error.

Give each confirmed problem the next `F-...` ID with: RCs or regression label, oracle, severity (critical: loss,
disclosure or main flow blocked; medium: wrong behavior; minor: limited cosmetic impact), blocking status,
role, minimal steps, expected and actual result, and evidence. A confirmed RC violation blocks even when it looks
minor. Attribute a regression only with evidence about prior behavior; otherwise mark it `pre-existing` or
`unknown`. Show the finding to the user right away (pause 5). When the finding ends a case as `FAIL`, finalize
any approved recording and show the evidence that demonstrates the failure.

## 9. Coverage and gate

Record each scenario as `PASS`, `FAIL`, `INCOMPLETE`, `NOT_RUN` or reasoned `N/A`, with round, expected and actual
result, time, role and evidence. Summarize every RC's coverage. List limitations (for example "Chromium only"),
untested areas, test data created and cleanup still needed.
Use the [evidence handoff rules](references/evidence.md#create-a-replay-and-hand-off-from-qa) for each case.
Open the [QA evidence view](references/interactive-ui.md#qa-results) after recording a round with screenshots
or recordings. Use the same report and show text results in chat for cases without visual evidence.
Show the evidence that demonstrates the result beside its `QA-ID` in chat. Record why expected evidence
is unavailable. If an approved retry passes, reference the failed attempt and its retained evidence separately.
Handle retest, false-positive decisions and comment drafts in chat, using the original scenario ID and round.
Save a confirmed user's false-positive decision with `summary --disposition` using the original `QA-ID`,
round, source `QA` and the user's reason. Follow [the decision command](../check/SKILL.md#record-a-round-and-its-decisions).

After QA, verify fresh scope evidence for each applicable pair using the same rules as before QA.
Changed code, scope, runner, profile,
requirements or runtime preparation make affected results stale. Mark the run `INCOMPLETE` and return to the
earliest affected stage.

For an approved plan, use the [QA gate command](references/gate.md) to check the recorded scenario outcomes
and requirement coverage. Read the reported stage status and save the output with the round. Exit `1` with
a valid `FAIL` result records a failed required case.

- `FAIL`, `can_proceed: false`: a confirmed blocking defect or a failed required scenario remains.
- `INCOMPLETE`, `can_proceed: false`: a required case is unexecuted, evidence or access is missing, a question is
  open, or an earlier gate or the environment is stale.
- `PASS`, `can_proceed: true`: the current plan is approved, every required scenario passed in this or a carried-over
  round with evidence, every RC is covered, and nothing blocking or unresolved remains.
- `N/A`, `can_proceed: true`: no QA scenario applies and other current verification covers every acceptance condition.

Close only sessions this run opened, keep evidence, and remove test data only within the agreed cleanup. Return
to `check` for the verdict. Do not fix code here: `check` offers the fix. Do not install dependencies, change Git
state, publish anything, or start another AI harness.
