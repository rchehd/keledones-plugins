# Changes to automated tests

Use this checklist when the task adds, changes or removes automated tests, including test-only diffs and
changes to runner config, fixtures, helpers and CI discovery. Identify the requested behavior and the
diagnostic outcome the test must prove. Read the corresponding assertions, entry points and existing test
conventions. For a test-only task, the acceptance conditions describe the coverage being delivered and
the expected runner result. The application can already implement the behavior.

## Evaluate coverage against the requirements

Use [ISTQB CTFL v4.0.1](https://istqb.org/?sdm_process_download=1&download_id=3345) §1.4.4 for traceability
and §4.2 for the coverage criteria below. This review applies at any test level, including unit, kernel,
integration and browser tests. Inspect coverage from the code even when the runner is unavailable.

1. Identify the expected test conditions from each affected acceptance criterion, agreed regression or
   project test requirement. Derive them independently of the cases currently in the suite. Select the
   techniques that fit the behavior and record the expected observable outcome for each condition.

   | Requirement pattern | ISTQB technique | Coverage to inspect |
   | --- | --- | --- |
   | Inputs or configurations with distinct outcomes | Equivalence partitioning (§4.2.1) | A representative for each relevant valid and invalid class. Check invalid classes in isolation where one invalid input could mask another. |
   | An ordered range with a limit or cutoff | Boundary value analysis (§4.2.2) | The boundary and neighboring inputs required by the chosen two-value or three-value analysis. Check outcomes on both sides of the change in behavior. |
   | Several conditions determine an outcome | Decision table testing (§4.2.3) | Each relevant feasible rule with a distinct combination of conditions. Combine rules where a condition has no effect. |
   | Prior state or a sequence changes the result | State transition testing (§4.2.4) | The required transitions and relevant rejected transitions. Check the resulting state as well as the immediate response. |

2. Trace each condition to the actual test setup, action and assertion. Consider existing tests that
   exercise the same requirement, including parameterized cases. Cite the test and assertion at their
   file and line. Count only cases eligible to run in the intended suite. If the only matching case is
   disabled or excluded, record the gap and the configuration or marker causing it. For a regression,
   consider whether the original defect could recur while the assertion still passes. A test name,
   a broad mock or a green suite summary alone does not establish coverage.
3. Record one row per condition in the report's **Automated test coverage** table. Use `COVERED` when
   the inspected test exercises the condition and asserts its full expected result, `PARTIAL` when it
   asserts only part of the outcome, `MISSING` when no effective test covers it, or `UNRESOLVED` when the
   expected behavior or essential code evidence is unclear. Describe the specific gap or question.
   These are code review conclusions. QA records whether the tests actually ran.

For example, for a 500-character limit, three-value boundary analysis expects cases at 499, 500 and 501.
A test that asserts rejection at 501 covers that condition. If the suite lacks a case at 500, record the
missing assertion that the maximum valid value is accepted.

Apply the normal review finding rules. Missing agreed coverage or a test that fails to enforce the
behavior it is required to prove is a requirement gap. Additional useful cases beyond the agreed test
scope can be suggestions. If the expected outcome is ambiguous, record a question rather than deriving
it from the implementation under review.

## Review test code and runner configuration

- Check that the intended runner and CI job discover the changed cases. Inspect file globs, suite type,
  project selection, tags, skip/only markers and retries. For shared fixtures or runner configuration,
  identify existing consumers and the coverage they could lose.
- Check isolation, deterministic fixtures and the scope of mocks or snapshots. Watch for hidden test order
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
