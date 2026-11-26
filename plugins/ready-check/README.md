<p align="center">
  <img src="assets/logo.png" alt="Ready Check" width="96">
</p>

# Ready Check · Review & QA

A plugin for Cursor, Claude Code and Codex that checks whether a task is ready to push. It traces the task's
requirements through static checks, code and security review, and behavioral QA in your current chat.
The skills apply the engineering and testing practices described in [Foundations](#foundations).

## How it works

```mermaid
flowchart LR
    Task["Task and acceptance criteria"] --> Scope["Choose full or partial scope"]
    Scope --> Checks["Run selected checks in order<br/>Static checks, review, QA with an approved plan"]
    Checks --> Report["Record evidence, findings and verdict"]
    Report -->|"Fix or retest"| Checks
    Report -->|"When eligible and requested"| Delivery["Draft or open a PR/MR"]
```

Choose all applicable stages or a partial scope. The report records which stages ran.

1. **Task and requirements.** The agent takes the task from the chat, a file or the prompts Ready Check recorded
   for the branch, asks only what changes the expected result, and writes requirements `RC-001`, `RC-002`, … with
   acceptance conditions. Progress is tracked in the client's own task list and in a report.
2. **Static checks** run the framework profile's checkers on the task's lines only.
3. **Review** traces every requirement through the code, applies shared and profile checklists for the kinds of
   changes found (configuration, forms, cache, access…), checks code quality (design fit, simplicity, names,
   comments, errors, dead code), reviews tests when the change has them, confirms a bug fix removes the cause,
   and applies your own coding rules. Findings are labelled `issue (blocking)`, `suggestion`, `nitpick` or
   `question`; only issues block.
4. **QA** ranks changed areas by risk and shows the plan for approval. It tests browser, native mobile,
   desktop, API, CLI and CI outcomes as applicable, with accessibility and exploration for browser cases.
5. **Verdict.** `READY TO PUSH` requires complete current validation and opens the delivery choice.
   Other runs report `BLOCKED`, `INCOMPLETE` or `PARTIAL CHECK COMPLETE`. Findings come with a fix offer.
   After a fix or "retest", the next round reruns only what the change can affect.

Plugin hooks do the rest without being asked: the agent offers a check after finishing a task, installs tools
after one consent, records your prompts per branch and passes your coding rules into every session.

| Skill | Claude Code / Cursor / Codex | Example request |
| --- | --- | --- |
| `check` | `/ready:check` · `/check` · `$check` | “Check this before I push.” “Run only static checks.” “Retest after the fix.” |
| `review` | `/ready:review` · `/review` · `$review` | “Use Ready Check to review these changes for correctness and security.” |
| `qa` | `/ready:qa` · `/qa` · `$qa` | “Do only CLI QA for this behavior.” “Plan browser QA for this flow.” |
| `draft` | `/ready:draft` · `/draft` · `$draft` | “Write a commit message.” “Draft the PR description.” “Generate a task comment about what I did.” |
| `setup` | `/ready:setup` · `/setup` · `$setup` | “Set up Ready Check.” “Change the profile or runner for this project.” |
| `customize` | `/ready:customize` · `/customize` · `$customize` | “Remember this coding rule for this project.” “Use my template for task comments.” |
| `feedback` | `/ready:feedback` · `/feedback` · `$feedback` | “QA returned this task. Record the reason in Ready Check.” |
| `reflect` | `/ready:reflect` · `/reflect` · `$reflect` | “Show my Ready Check stats.” “Where do my tasks get stuck before PR?” |
| `contribute` | `/ready:contribute` · `/contribute` · `$contribute` | “Prepare a contribution for this improvement to the Ready Check plugin.” |
| `uninstall` | `/ready:uninstall` · `/uninstall` · `$uninstall` | “Preview what uninstalling Ready Check would remove.” |

Ask for draft text whenever you need it, including while a task is in progress. Git and tracker actions
require a separate publication request or delivery choice.

Checks live in framework profiles. See [supported profiles](#supported-profiles) for available stacks and checkers.

## Foundations

Ready Check defines the workflow for selecting checks, approving a QA plan, collecting evidence, making
fix decisions and issuing a verdict. The sources below inform the checks within that workflow.

| Stage | Built on |
| --- | --- |
| Requirements | Acceptance conditions per requirement and traceability from requirement to evidence, as in requirement-based testing |
| Static checks | The project's own linters first, then the framework's established tools: Drupal Coder (PHPCS) and phpstan-drupal; Pint and Larastan; PHP-CS-Fixer `@Symfony`, phpstan-symfony and the `bin/console` linters; Ruff, mypy, Bandit and Django system checks; gofmt, go vet, golangci-lint (staticcheck, errcheck, gosec) and govulncheck; ESLint and Stylelint for assets |
| TypeScript and YAML | [TypeScript Compiler API](https://github.com/microsoft/TypeScript/wiki/Using-the-Compiler-API) and [project references](https://www.typescriptlang.org/docs/handbook/project-references.html) for type checking, [typescript-eslint](https://typescript-eslint.io/getting-started/) for linting, and [yamllint](https://yamllint.readthedocs.io/en/stable/configuration.html) for plain YAML |
| Infrastructure checks | [actionlint](https://github.com/rhysd/actionlint/blob/main/docs/usage.md) for GitHub Actions, [Compose config](https://docs.docker.com/reference/cli/docker/compose/config/), [DDEV utilities](https://docs.ddev.com/en/stable/users/usage/commands/) and [Nginx configuration testing](https://nginx.org/en/docs/switches.html). [GitLab CI Lint](https://docs.gitlab.com/ci/yaml/lint/) validates the effective pipeline and its includes on GitLab. |
| Flutter checks | [Flutter CLI](https://docs.flutter.dev/reference/flutter-cli) for analysis and project tests, and [Dart format](https://dart.dev/tools/dart-format) for formatting checks |
| Review | [Google code review guide](https://google.github.io/eng-practices/review/reviewer/looking-for.html) for functionality, design, complexity and tests, [Conventional Comments](https://conventionalcomments.org/) for finding labels, [ub-mode](https://github.com/unclebob/ub-mode) for root causes and tests that verify behavior, and the [OWASP Code Review Guide](https://owasp.org/www-project-code-review-guide/) for security. Profile checklists add version-specific framework guidance. Selected static checks run before review. Every blocking finding cites a file, line and cause. |
| Framework review | Security guidance for [Laravel](https://cheatsheetseries.owasp.org/cheatsheets/Laravel_Cheat_Sheet.html), [Symfony](https://cheatsheetseries.owasp.org/cheatsheets/Symfony_Cheat_Sheet.html), [Django](https://cheatsheetseries.owasp.org/cheatsheets/Django_Security_Cheat_Sheet.html) and [Go](https://go.dev/doc/security/best-practices). See also the [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) and Drupal guidance on [configuration updates](https://www.drupal.org/docs/drupal-apis/update-api/updating-configuration), [render cacheability](https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays) and [secure code](https://www.drupal.org/docs/administering-a-drupal-site/security-in-drupal/writing-secure-code-for-drupal). |
| Shared review checklists | [OWASP ASVS](https://asvs.owasp.org/) for web and API security, [Parallel Change](https://martinfowler.com/bliki/ParallelChange.html) for staged migrations, and [AWS Builders' Library](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) for idempotent retries |
| QA design | Risk-based testing prioritizes by likelihood and impact. [ISTQB CTFL](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf) and [ISO/IEC/IEEE 29119-4](https://www.iso.org/standard/79430.html) inform the test design. Use equivalence partitioning, boundary values, state transitions and decision tables for specified behavior, and use error guessing as an experience-based technique. |
| [Review results template](templates/review-results.md) | Adapted from the Review Report in Annex A.4 of ISO/IEC 20246. Finding labels follow Conventional Comments. [ISO/IEC 20246:2017](https://www.iso.org/standard/67407.html) · [Conventional Comments](https://conventionalcomments.org/) |
| [QA plan template](templates/qa-plan.md) | Adapted from the Test Plan (§7.2) and Test Case Specification (§8.3), with planning guidance from ISTQB CTFL §5.1.1. [ISO/IEC/IEEE 29119-3:2021](https://www.iso.org/standard/79429.html) · [ISTQB CTFL](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf) |
| [QA results template](templates/qa-results.md) | Adapted from the Test Completion Report (§7.4) and ISTQB CTFL §5.3.2. [ISO/IEC/IEEE 29119-3:2021](https://www.iso.org/standard/79429.html) · [ISTQB CTFL](https://istqb.org/wp-content/uploads/2024/11/ISTQB_CTFL_Syllabus_v4.0.1.pdf) |
| QA oracles and exploration | Use [HICCUPPS consistency oracles](https://developsense.com/resource/Oracles.pdf) where the requirement leaves an outcome unclear. Use SFDPOT, adapted from the [Heuristic Test Strategy Model](https://www.satisfice.com/download/heuristic-test-strategy-model), and charters from [Session-Based Test Management](https://www.satisfice.com/download/session-based-test-management) for focused exploration. |
| Bug reports | RIMGEA (Kaner's bug advocacy): replicate, isolate, maximize, generalize, externalize; steps, expected and actual result, severity, evidence |
| Browser automation | [Playwright best practices](https://playwright.dev/docs/best-practices): user-facing locators, web-first waits, isolated sessions; official Playwright CLI and MCP |
| Automated test changes | [ISTQB CTFL v4.0.1](https://istqb.org/?sdm_process_download=1&download_id=3345) (§1.4.4 and §4.2) for reviewing requirements coverage against existing assertions. [Playwright Test](https://playwright.dev/docs/test-cli) and [Cypress best practices](https://docs.cypress.io/app/core-concepts/best-practices) for browser test review and targeted runs. |
| QA recording | Capture approved cases from the first attempt and keep failure footage even when a retry passes. [Playwright retention modes](https://playwright.dev/docs/test-use-options#video-modes) · [Cypress video retention](https://docs.cypress.io/app/guides/screenshots-and-videos#delete-videos-for-specs-without-failing-or-retried-tests) |
| Web platform review | [Modern Web Guidance](https://developer.chrome.com/docs/modern-web-guidance) and [Baseline](https://web.dev/baseline) for browser compatibility, progressive enhancement and fallback scenarios |
| Technical QA | Project tests and fixtures, [OpenAPI](https://spec.openapis.org/oas/latest.html) for API contracts, and [CI run evidence](skills/qa/references/technical-qa.md#ci-and-artifacts) tied to the tested revision |
| Design and native QA | [Figma Dev Mode and MCP](https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/) for agreed design references, existing [Flutter integration tests](https://docs.flutter.dev/cookbook/testing/integration/introduction), [Maestro](https://docs.maestro.dev/get-started/supported-platform/flutter) for device flows, and [OWASP MASVS](https://mas.owasp.org/MASVS/) for mobile security |
| Learning from use | Cursor's [`/reflect`](https://github.com/cursor/plugins/blob/main/pstack/skills/reflect/SKILL.md) and [Continual Learning](https://github.com/cursor/plugins/tree/main/continual-learning), [CodeRabbit Learnings](https://www.coderabbit.ai/blog/context-engineering-ai-code-reviews): proposals backed by evidence, applied only after approval |
| Accessibility | [axe-core](https://github.com/dequelabs/axe-core) on changed pages plus manual keyboard and focus checks, since automated rules find only part of WCAG issues ([Deque coverage study](https://www.deque.com/blog/automated-testing-study-identifies-57-percent-of-digital-accessibility-issues)) |

## Install

Ready Check lives in the [Keledones](https://github.com/rchehd/keledones-plugins) plugin catalog (`plugins/ready-check`).

Claude Code:

```sh
claude plugin marketplace add rchehd/keledones-plugins
claude plugin install ready@keledones
```

Codex:

```sh
codex plugin marketplace add rchehd/keledones-plugins
codex plugin add ready@keledones
```

Then open `/hooks` in Codex and trust the plugin's three hooks; Codex runs them only after that and may ask
again after each plugin update.

Cursor: **Customize → From GitHub Repository** with `rchehd/keledones-plugins`, or a team admin adds it under
**Dashboard → Plugins & MCPs → Add Marketplace → Import from Repo**.

For development, add the local Keledones checkout path. To install Ready Check on its own, follow the
[individual plugin instructions](https://github.com/rchehd/keledones-plugins#install-an-individual-plugin).

## Use

Open the application you want to check and start a chat. On the first session in a project the agent shows what
Ready Check detected (for example "Drupal 11, DDEV" or "Laravel, Compose") and asks once whether to install Playwright, Chromium and the
framework checkers. Confirm or correct the project type; on yes the tools install in the chat and the agent ends
with "Ready Check is ready". Downloads are agreed once per machine, the project type once per project. On no,
nothing is downloaded and the question is not repeated; review, reminders and task records still work.

After you finish a task that changed the project, the agent offers checks based on the changed behavior,
paths and applicable profiles. A workflow change can get CI QA, while a changed web flow and API can get both
Playwright and API QA. Choose all checks, static + review, QA only, another combination, or turn the offers
off for the rest of the session. You can also start a check yourself
with the commands in [How it works](#how-it-works).

**Test-only tasks.** Ready Check reviews the coverage, assertions and fixtures of added or changed tests.
QA runs the selected cases with the project's own runner, such as Playwright Test or Cypress, and records
which cases executed. Use the project's configured environment and its installed test tools. See the
[test review checklist](skills/review/references/automated-tests.md) and
[project test runner guidance](skills/qa/references/project-tests.md).

Ready Check loads its instructions through plugin hooks. In Codex, trust the plugin's hooks in `/hooks`.
Cursor gets the rule at session start and again with the first message of each chat, because its session-start
context can arrive after that message. Cursor has no end-of-turn reminder.

**QA.** The agent ranks changed areas by risk, designs cases with standard techniques (equivalence classes,
boundary values, state transitions, decision tables), shows the plan for approval, then runs it. Browser cases
use Playwright, axe-core and manual keyboard and focus checks. API and CLI cases use project tools or direct
tests, and CI cases inspect the matching run, job and artifact. Native mobile cases use existing device tests
or Maestro on the provisioned target. When a task has an agreed Figma reference, QA compares the matching
viewport, variant and state against that reference. All results go into the same report. The agent posts the
plan or the relevant findings before asking you to approve the plan or choose how to fix an issue. It uses the
client's native question tool when available. You can fix the issue yourself, ask the agent to fix it here,
or delegate the fix to a subagent where supported. After a fix or a "retest", Ready Check reruns affected
static checks, reviews changed code and its callers, and reruns failed or related QA cases and each RC's main
flow. Shared-code changes or a request for a full recheck rerun the whole plan.

**QA evidence.** The agent posts a Markdown summary with failures first and links to the screenshots and
recordings that support each result. Clients with media previews can display selected evidence inline.
The local HTML report keeps the color-coded cards, full-size screenshot comparisons and video players
with chapter controls. [QA evidence and HTML report](skills/qa/references/interactive-ui.md)

**PhpStorm.** After a full setup, choose whether to connect its optional MCP inspections. You can also
say "Connect PhpStorm MCP" later. In Cursor, after opt-in, Ready Check registers the running PhpStorm MCP
in the project's `.cursor/mcp.json`. With the right project open in the IDE and the inspection tools available,
review can use IDE warnings and errors as evidence candidates. [Connection guide](skills/setup/references/phpstorm.md)

**Browser.** For interactive web scenarios, choose **Background Playwright** (headless) or
**Visible Playwright** (an open browser window for watching and manual sign-in). To save a default, use
`config set browser background|visible`. Use the project's runner for its existing specs.
[Browser modes guide](skills/qa/references/playwright.md)

**Recording.** The agent journals the actions and observed results of executed cases. During QA plan approval,
choose which browser or mobile cases to record. Recording starts on the first attempt. A routine `PASS` gives
you the result and journal, and its temporary video is discarded. A `FAIL` gives you the failed attempt's video
when available, including failures on the first attempt. If a retry passes, you still get the failed attempt's
video with the final `PASS`. Saved clips live with the QA report so later runs can clean their own output.
Request a demo or make video part of the acceptance criteria to get video of a successful attempt too.
The bundled Chromium supports captions, a pointer and target highlighting, and the
local player can seek to steps in the journal.
[QA action journal and video](skills/qa/references/evidence.md).

**Language.** Reports, QA plans and handoffs follow the chat language by default. Choose a language for one
task in chat or save a preference with `config set artifactLanguage Ukrainian`. Use `chat` to restore the default.
Commit messages, PR/MR text and machine-readable report keys stay in English.

**Delivery.** If selected checks pass, choose to see the English commit message and PR/MR text in chat or
open a PR/MR. A partial run also offers the outstanding checks and keeps its partial verdict if you proceed
to delivery. To create a PR/MR, your client needs an authenticated `gh`, `glab` or connector. The agent shows
the branches and any required commit or push before you choose. After delivery it offers a first-person
task-comment draft in the current chat's language.

**Draft templates.** Set `commitTemplate`, `pullRequestTemplate` and `taskCommentTemplate` to your own files.
Project and global overrides are available in every client. See the
[template settings](dependencies/SETUP.md#commit-pr-and-task-comment-templates).

**Task memory.** Each prompt you send, and each answer you pick in the agent's questions, is saved with branch,
commit and time in `.ai/ready-check/tasks/<branch>/` (git-excluded, cut at 20 KB, kept 30 days). When the task is not in the chat, `check` proposes it from these
records and asks you to confirm. Turn off with `config set captureTasks false`.

**Coding rules.** Add your own rules, for example "Prefer switch over long if/elseif chains" or "Flag comments
longer than two lines". The session hook gives them to the agent in every chat, and the review checks changed code
against them. A rule that starts with `MUST:` blocks the review; others are recommendations. Sources:

- Claude Code: the plugin's **Coding rules** setting (shown when the plugin is enabled); Cursor: the plugin
  variable `READY_CHECK_RULES`, one rule per line.
- Any client: tell the agent "remember the rule …" (the `customize` skill), saved globally or for the project.

Settings and commands: [setup guide](dependencies/SETUP.md).

## Customize and improve

Ready Check changes its behavior through files you own, never by editing the plugin, so plugin updates keep them.

```text
<data folder>/                        global: all your projects (~/.local/share/ready-check on Linux)
├── rules.md
└── extensions/<profile>/review.md, qa.md

<repo>/.ai/ready-check/                project: git-excluded by default
├── rules.md
├── extensions/<profile>/review.md, qa.md
├── feedback.jsonl, reports/, tasks/, settings.json   always local
```

On upgrade, Ready Check moves local entries from `ai/ready-check/` into `.ai/ready-check/` automatically.
Git-tracked files stay in place until your team moves them. Shared rules and checklists remain active alongside
new local items. Ready Check keeps legacy journals available to older clients, reads both locations without
counting entries twice, and applies task-log retention to both. Files copied across filesystems keep their legacy
copies. The active Git commit template stays at its configured path.

If the same report already exists in both folders, each copy keeps its own evidence and the report in
`.ai/ready-check/` remains active. A legacy branch-level report can coexist with dated tasks and keeps its original
`task_id`. Markdown links and JSON evidence references are updated to point to migrated evidence.

- **Rules** act in every session and in every review (`MUST:` rules block). **Extensions** add items to a section of
  the profile's review or QA checklist, for example "I. Render output, templates and cache".
- **Add or change** them with `customize`: "add a review check for forms to the project", "show my rules",
  "disable that rule". Disabling in a project also hides a global item or a client-settings rule there.
- **Share with the team:** `git add -f .ai/ready-check/rules.md .ai/ready-check/extensions` and commit; reports, task
  records, feedback and settings stay local.
- **Feedback:** when a lead or QA returns a checked task, say so ("the task was returned…"); the agent asks and
  records it with `feedback`: who, why, and whether Ready Check missed it.
- **Reflect:** "show my Ready Check stats" gives an overview of the last 10 tasks (rounds, defects, returns, typical
  errors) in chat and saves an offline HTML report in `.ai/ready-check/reflect/`. Only if you ask does it propose
  improvements; for each you choose any of: project, global, PR to Ready Check, skip.
  For a private portrait of how you give instructions, delegate and redirect agents, use the
  [Gnothi portrait](https://github.com/rchehd/keledones-plugins/tree/main/plugins/gnothi).
- **Contribute:** general improvements go to the Ready Check repository as a pull request from the
  [improvement template](templates/improvement.md), prepared by `contribute` and published only
  after your yes. No client code or data leaves your environment; see [CONTRIBUTING](CONTRIBUTING.md).

**Check a task** by describing the task or pointing to it. You can ask for all checks or only some:
static, review, or QA. To check specific commits instead of the whole branch, name them:

> /check — check commits a1b2c3d and e4f5a6b against TASK.md

The agent asks when something is unclear and pauses for your approval of the QA plan. When it finds a
problem, it asks whether to fix it or leave it to you, then rechecks after the fix. Commit and push are part
of delivery only when you select creation with those operations.

The Git-excluded report lives at `.ai/ready-check/reports/<branch-slug>/<task-id>/report.md`. The branch
directory combines a readable slug and a hash of its full name. A later chat can resume the same task by
using its task ID or report path.

## Verdicts

| Verdict | Meaning |
| --- | --- |
| `READY TO PUSH` | All checks passed for the current code and every requirement is covered |
| `BLOCKED` | A confirmed problem was found |
| `INCOMPLETE` | Something is missing: an answer, a tool, access or evidence |
| `PARTIAL CHECK COMPLETE` | The selected checks passed; the others were not run |

## Supported profiles

Each profile supplies detection rules, setup, static checks, and review/QA guidance for its scope.
Shared skills load these rules from each applicable profile. Required checks run when their inputs apply;
advisory checks report findings or missing tools without blocking the static gate.

- **[Drupal 10/11](profiles/drupal/static.md)** — profile ID: `drupal`.
  - **PHPCS** — PHP coding standards; defaults to Drupal and DrupalPractice rules.
  - **PHPStan** — static PHP analysis with Drupal integration and deprecation rules.
  - **PHP/YAML syntax** — `php -l` and the Symfony YAML parser.
  - **ESLint / Stylelint** — JavaScript and CSS/SCSS checks.
  - **Twig CS Fixer** — Twig template linting, without auto-fix.
  - **Composer validate** — dependency manifest and lock-file consistency.
  - **Debug leftovers** — checks for debugging calls and statements.
  - **Git diff formatting** — whitespace/error checks.
  - **Module configuration** — checks packaged Drupal configuration for site-specific UUID/hash values.
  - **jscpd** — duplication detection; advisory.
  - **PHPMD** — code-size and unused-code checks; advisory.
  - **Composer audit** — dependency security advisories and abandoned packages; advisory.
  - **Dead-code detector** — optional PHPStan extension; disabled by default and not included in managed dependencies.

- **[Laravel 12+](profiles/laravel/static.md)** — profile ID: `laravel`; Sail, DDEV or local.
  - **Pint** `--test` (project `pint.json` wins), **PHPStan with Larastan** (default level 5), `php -l`,
    debug leftovers (`dd`, `dump`, `ray`, `var_dump`), diff, ESLint/Stylelint for Vite assets, `composer validate`.
  - Advisory: **Rector** `--dry-run` with the Laravel set, `composer audit`, jscpd, PHPMD.
- **[Symfony 7.4+](profiles/symfony/static.md)** — profile ID: `symfony`; Docker Compose, DDEV or local.
  - **PHP-CS-Fixer** `@Symfony` when the project has a config (else PHPCS PSR-12), **PHPStan with
    phpstan-symfony** (and phpstan-doctrine with Doctrine), `php -l`, `lint:container`, `lint:yaml`,
    `lint:twig`, `lint:xliff` when their inputs changed, debug leftovers, diff, `composer validate`.
  - Advisory: `doctrine:schema:validate`, `composer audit`, jscpd, PHPMD.
- **[Python](profiles/python/static.md)** (Django, FastAPI, Flask) — profile ID: `python`; project venv, uv,
  Poetry or Compose.
  - **Ruff** lint and `ruff format --check` (project config wins), **mypy** when the project configures it,
    syntax, debug leftovers (`breakpoint()`, `pdb`, `print(` in app code), diff; Django: `manage.py check` and
    `makemigrations --check --dry-run`.
  - Advisory: **Bandit**, **pip-audit**, jscpd.
- **[Go](profiles/go/static.md)** — profile ID: `go`; local or Compose.
  - **gofmt**, **go vet**, **golangci-lint** (project config wins; default enables staticcheck, errcheck,
    gosec, govet, ineffassign, unused), `go build`, debug leftovers (`spew.Dump`, `"DEBUG` prints,
    `println`), diff.
  - Advisory: **govulncheck**, jscpd.
- **[Generic](profiles/generic/static.md)** — profile ID: `generic`; any language or a mixed-language repository.
  - Git diff checks, syntax checks for Python, plain JSON, YAML and POSIX sh/Bash, and project-specific lint and test
    commands recorded by the check skill. Profile setup uses the existing tools on the selected host.
- **[TypeScript](profiles/typescript/static.md)** — profile ID: `typescript`.
  - TypeScript type checking with project configs and references, and ESLint for changed TypeScript files.
    Uses project tools and configs first. The managed fallback includes official typescript-eslint rules.
- **[DevOps](profiles/devops/static.md)** — profile ID: `devops`.
  - GitHub Actions with actionlint, Docker Compose, DDEV and Nginx validation, and GitLab YAML syntax.
    Uses installed tools. GitLab CI Lint adds provider checks for the effective pipeline and its includes.
- **[Flutter](profiles/flutter/static.md)** — profile ID: `flutter`.
  - Uses the project's Flutter SDK for analysis and the bundled Dart formatter. QA reuses the project's
    unit, widget and device tests, with Maestro for applicable native flows.

Project tools and configs take priority over pinned tools installed outside the project. Projects can use
several profiles in one directory or across application roots. When no specific profile matches, Ready Check
uses `generic`. You can also select `generic` explicitly. New profiles belong under
`profiles/<id>/` and reuse `profiles/_shared/` ([adding a
profile](dependencies/SETUP.md#adding-another-profile)).

## Configuration

The profiles you confirm at first run are stored in `.ai/ready-check/settings.json` (git-excluded) and take
precedence over the repository's optional `.ready-check.json`. To share selections with your team, use:

```json
{
  "profiles": [
    {"profile": "drupal", "runner": "ddev", "application": "."},
    {"profile": "python", "runner": "local", "application": "tools"}
  ]
}
```

`application` is relative to the repository root. `runner` can be `local`, `ddev` or `compose`.
Existing scalar `profile`, `runner` and `application` settings still define one selection. When the legacy
runner is omitted, it is detected from project markers. `LINT_SERVICE` and `LINT_CONTAINER_ROOT` pick the
Compose service and root. The `ready-check.py profiles --project <repo>` command shows selections and evidence.
Project tools and configs (`vendor/bin`, `phpcs.xml`, `phpstan.neon`, `pint.json`, `.php-cs-fixer.dist.php`,
`[tool.ruff]`, `.golangci.yml`, ESLint/Stylelint configs) take priority over the managed ones.

## Requirements

- Python 3.9+ and Git (Linux, macOS, Windows, WSL).
- Node.js 20+ and npm on the host for the browser.
- For Drupal checks: PHP 8.2+, Composer, Node.js 20+ and npm in the selected runner.
- For Laravel and Symfony checks: PHP 8.2+, Composer, Node.js 20+ and npm in the selected runner.
- For Python checks: Python 3.10+ in the runner for the managed tools; the project's own interpreter for
  Django checks.
- For Go checks: Go 1.26+ in the runner (the pinned golangci-lint needs it); Node.js 20+ for asset checks.
- For TypeScript checks: Node.js in the runner. Managed setup requires Node.js 20+ and npm.
- For YAML checks in Generic: `yamllint` in the selected runner.
- For DevOps: the tools that match the changed files, as listed in the [DevOps profile](profiles/devops/static.md).
- For Flutter: the project's prepared Flutter SDK and packages. Native device cases need a suitable test target.

## Documentation

- [Setup details](dependencies/SETUP.md)
- [Review skill](skills/review/SKILL.md) and [shared review checklist](skills/review/references/change-types.md)
- [QA test design](skills/qa/references/test-design.md) and [what evidence to keep and show](skills/qa/references/evidence.md#create-a-replay-and-hand-off-from-qa)
- Static checks: [Drupal](profiles/drupal/static.md), [Laravel](profiles/laravel/static.md),
  [Symfony](profiles/symfony/static.md), [Python](profiles/python/static.md), [Go](profiles/go/static.md),
  [TypeScript](profiles/typescript/static.md), [Flutter](profiles/flutter/static.md)
- [Report template](skills/check/references/report-template.md)

## Development

```sh
python3 -B scripts/validate-package.py
python3 -B -m unittest discover -s tests
claude plugin validate --strict .
```

For a release, raise the version in all three plugin manifests at once; clients detect updates by this version:

```sh
python3 -B scripts/bump-version.py 0.2.0
```

To remove Ready Check, run `uninstall` first (it previews, then removes project settings and, on request,
reports, task records and installed tools), then remove the plugin with your client's plugin controls.
Uninstall leaves the Ready Check entries in Git's `info/exclude` to protect private data in other worktrees
and sessions.
