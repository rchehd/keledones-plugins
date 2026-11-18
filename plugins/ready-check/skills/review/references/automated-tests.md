# Changes to automated tests

Use this checklist when the task adds, changes or removes automated tests, including test-only diffs and
changes to runner config, fixtures, helpers and CI discovery. Identify the requested behavior and the
diagnostic outcome the test must prove. Read the corresponding assertions, entry points and existing test
conventions. For a test-only task, the acceptance conditions describe the coverage being delivered and
the expected runner result. The application can already implement the behavior.

- Check that the intended runner and CI job discover the changed cases. Inspect file globs, suite type,
  project selection, tags, skip/only markers and retries. For shared fixtures or runner configuration,
  identify existing consumers and the coverage they could lose.
- Trace setup, action and assertion. Check that the assertion would catch the named regression, that broad
  mocks or snapshots do not erase the target behavior, and that the new cases cover the agreed positive,
  negative and boundary paths. Use isolated fixtures and deterministic data. Watch for hidden test order
  dependencies, real credentials and unintended external calls.
- **Playwright Test:** prefer user-facing locators or the project's stable test IDs, isolated contexts and
  retrying locator assertions such as `await expect(locator).toBeVisible()`. Flag timing dependencies such
  as `waitForTimeout` used for readiness. Confirm assertions and asynchronous actions are awaited.
- **Cypress:** follow the project's stable selector convention, such as `data-cy`. Prefer retryable
  queries and `.should()` or wait for a relevant `cy.intercept()` alias. Check that the alias observes the
  intended request and that the assertions still exercise the behavior under test. Flag arbitrary
  `cy.wait(ms)` used for readiness and cross-test state dependencies.

Send the test IDs or spec paths, runner and expected result to [QA](../../qa/references/project-tests.md).
Map each case to the requirement or regression it covers. Report confirmed defects through the ordinary
review findings and leave execution results to QA.

[Playwright Test best practices](https://playwright.dev/docs/best-practices) ·
[Cypress best practices](https://docs.cypress.io/app/core-concepts/best-practices) ·
[Cypress retry-ability](https://docs.cypress.io/app/core-concepts/retry-ability)
