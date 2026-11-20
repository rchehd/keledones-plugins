# Verify changes to automated tests

When automated tests are a deliverable, include running the new or affected tests in the approved QA plan.
This applies to test-only changes too. Read the existing project's scripts, config and CI invocation to
discover the runner, suite type, spec selection, environment and version. Use the project's command and
already provisioned tools and fixtures. Plan the exact selection before executing it.

- For browser end-to-end or component tests, use browser cases with the **project test runner** as the
  execution method. Playwright Test runs its project config and selected spec files (and `--project` if
  relevant). Cypress runs the selected specs with its configured mode and browser, for example
  `cypress run --e2e --spec <file>` or `cypress run --component --spec <file>` through the project command.
  Set application URL, credentials and browser/project selection using the project's test configuration.
  Use a test environment with approved data. The separate Playwright MCP/CLI session is needed only for
  separately planned interactive browser cases.
- Before running, inspect effective recording settings in the config, selected project, environment and
  command. Disclose automatic recording in the QA plan and get approval for the affected scenarios.
  Verify the recording starts after authentication. Check the tests, setup projects, fixtures, hooks and
  session-recovery paths for login, reauthentication, account switching or credential entry during capture.
  If the runner cannot exclude those actions, or recording was declined, disable its video with a verified
  run-local override that preserves test selection and environment. Cypress supports `--config video=false`.
  For Playwright Test, use a project-supported config or wrapper whose effective `use.video` is `off`.
  Resolve unknown settings or the lack of an override before running. An approved separate recorder may
  start after authentication when it can cover the planned case. Otherwise record the capture limitation
  and use the journal and other allowed evidence. A required case without an authorized execution method
  or required evidence is `INCOMPLETE`. Uploads require separate authorization, including Cypress Cloud's
  `--record` mode.
- Before launching a runner that clears or overwrites its artifacts, give each invocation a fresh, empty
  output location outside the worktree or in a Git-ignored directory. Keep runner output separate from the
  task report and stored evidence. Playwright Test clears `outputDir` at startup. Use `--output <run-dir>`
  or a verified project-supported equivalent. Cypress clears `videosFolder`, `screenshotsFolder` and
  `downloadsFolder` by default. Point each to a dedicated subdirectory of the fresh run directory using
  run-local config. Apply this isolation when recording is disabled too. If the project invocation cannot
  isolate its output safely, resolve the cleanup risk before starting or use an approved fallback.
- For approved failure footage that meets the authentication rule above, use a runner setting that records
  the first attempt and retains failed attempts even if a retry passes. Playwright Test supports
  `use.video: 'retain-on-failure'` for retention. It can record authentication that happens during the test.
  Use a recording mode that keeps successful clips for approved demos and required video. If the available
  runner cannot capture the first attempt, disclose that limitation in the plan or use an approved fallback.
- For suites that exercise an API, a device or a CLI, use the corresponding scenario kind. Record a
  local runner invocation for unit, kernel or other service integration tests as a CLI scenario.
  Use CI cases when the requirement concerns test discovery, configuration or artifacts in the hosted
  pipeline. Record the actual tool, version, working directory, environment, exact command or scoped CI
  job and tested revision.
- Confirm that the intended test names and project(s) actually ran. Record outcomes, skipped or
  filtered cases, retries and any flaky results. A zero exit code with zero matching tests leaves the
  planned case unverified. Capture a redacted runner summary and relevant traces, screenshots or logs.
  Associate each retained clip with the test and attempt it shows, even if the final run passed. Copy the
  clips selected by the [retention policy](evidence.md#create-a-replay-and-hand-off-from-qa) into their prepared
  evidence directories before a separate rerun, cleanup, or chat handoff. Link only those copies or their
  replays. Run affected neighboring
  specs when shared config or fixtures changed, or repeat a focused case when investigating a timing or isolation issue.
- For regression tests, use a safe agreed baseline or isolated fixture to show the assertion catches
  the original failure when feasible. Do not mutate tracked application code or switch branches for
  this proof. If a safe baseline is unavailable, record what was demonstrated by the current run and
  what supports the regression claim from review. If the runner, browser or test environment is missing,
  record the missing evidence as `INCOMPLETE` for the affected required case. A separate browser probe
  can prove UI behavior but cannot prove that the delivered spec ran.

[Playwright Test CLI](https://playwright.dev/docs/test-cli) ·
[Playwright output directory](https://playwright.dev/docs/api/class-testconfig#test-config-output-dir) ·
[Cypress command line](https://docs.cypress.io/app/references/command-line) ·
[Cypress artifact cleanup](https://docs.cypress.io/app/references/configuration#trashAssetsBeforeRuns)
