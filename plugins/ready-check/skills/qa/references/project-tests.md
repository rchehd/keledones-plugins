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
- For suites that exercise an API, a device or a CLI, use the corresponding scenario kind. Record a
  local runner invocation for unit, kernel or other service integration tests as a CLI scenario.
  Use CI cases when the requirement concerns test discovery, configuration or artifacts in the hosted
  pipeline. Record the actual tool, version, working directory, environment, exact command or scoped CI
  job and tested revision.
- Confirm that the intended test names and project(s) actually ran. Record outcomes, skipped or
  filtered cases, retries and any flaky results. A zero exit code with zero matching tests leaves the
  planned case unverified. Capture a redacted runner summary and relevant traces, screenshots, videos
  or logs when the project provides them. Run affected neighboring specs when shared config or fixtures
  changed, or repeat a focused case when investigating a timing or isolation issue.
- For regression tests, use a safe agreed baseline or isolated fixture to show the assertion catches
  the original failure when feasible. Do not mutate tracked application code or switch branches for
  this proof. If a safe baseline is unavailable, record what was demonstrated by the current run and
  what supports the regression claim from review. If the runner, browser or test environment is missing,
  record the missing evidence as `INCOMPLETE` for the affected required case. A separate browser probe
  can prove UI behavior but cannot prove that the delivered spec ran.

[Playwright Test CLI](https://playwright.dev/docs/test-cli) ·
[Cypress command line](https://docs.cypress.io/app/references/command-line)
