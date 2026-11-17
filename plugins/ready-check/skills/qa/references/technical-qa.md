# API, CLI and CI QA

Use the project's existing tests and documented commands first. Record the target and its revision or build,
actor or fixture, the action, expected behavior, actual result and redacted evidence in the task report.
For a carried result, verify its source, runtime, data and expected behavior still match the case.

## API

- Use the project's API tests, an existing HTTP client such as curl, or Playwright's API request context
  when already available. Verify method, route, status and relevant headers or response fields. If an
  OpenAPI contract exists, match the status and response shape to the applicable operation and version.
- Include the allowed role and a denied role or resource owner when authorization changes. Test the actual
  server response and verify that denied writes do not alter state. Treat an expected denial as passing
  when both the response and state match the plan.
- For a changed contract, use the project's compatibility check or an available tool such as oasdiff.
  Run generated schema cases with an approved test scope and data, for example through an existing
  Schemathesis setup. A schema check can support runtime evidence.

Record the request path and sanitized inputs and response fields. Resolve secrets through the project's test
setup and leave out authorization headers, cookies, tokens and private response data.

## CLI

- Use an isolated fixture and the project's shell or test runner. Run the documented entry point with the
  approved arguments and working directory. Verify the exit status, stdout/stderr, and relevant files or
  other state. If the requirement concerns retry behavior, run the same operation again when safe.
- Include the error path when it changes. Record an expected failure as passing when its exit code, error
  output and side effects match. For Bash projects, reuse existing Bats tests when available.
- Record which executable or package version ran, the fixture identity, and a redacted command and
  output excerpt. A missing executable, timed-out fixture, or otherwise unverified run is incomplete.

## CI and artifacts

- Use an existing provider run, a project tool, or provider UI/API evidence. Match the actual commit or
  tested build, workflow, event/ref, job or matrix entry and its outcome to the scenario. An earlier run
  for another commit, a skipped required job or missing job evidence leaves the scenario incomplete.
- When the deliverable changes, inspect the produced artifact and test the documented install or consume
  path if the requirement depends on it. Record artifact identity and evidence such as its manifest or
  digest. A local build can verify artifact contents. Provider execution needs evidence from the provider.
- Launch new jobs, upload data or deploy only when the user authorizes the specific operation.

Save sanitized evidence beneath the report's `evidence/` folder, or link the applicable provider evidence.
Report a confirmed mismatch as `FAIL` and missing access, setup or attributable evidence as `INCOMPLETE`.

[OpenAPI Specification](https://spec.openapis.org/oas/latest.html) ·
[Playwright API testing](https://playwright.dev/docs/api-testing) ·
[oasdiff](https://github.com/oasdiff/oasdiff) ·
[Schemathesis](https://schemathesis.readthedocs.io/en/stable/) ·
[Bats](https://bats-core.readthedocs.io/en/stable/writing-tests.html) ·
[GitHub Actions run history](https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/monitoring-workflows/viewing-workflow-run-history) ·
[GitLab pipelines](https://docs.gitlab.com/ci/pipelines/)
