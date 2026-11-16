# Dependency setup

Marketplace installation delivers the plugin's skills, scripts, profiles, hooks and lock files. Clients do not
run plugin code at install time, so tools are installed on the first session after installation, once the user
agrees. Tools go to managed data directories, never into the project's Composer/npm manifests, lock files,
`vendor/` or `node_modules/`. Setup does not install system PHP, Node.js, npm, Composer or OS browser libraries.

## First run

On a session start in a project without a confirmed project type, the session hook detects it from files only
(the profile from each profile's `detection` rules, for example `drupal/core` or `laravel/framework` in
`composer.json`, `manage.py`, `go.mod`; framework profiles win over language ones; the runner from
`.ddev/config.yaml` or a Compose file) and asks the agent to show one question before answering the first message: the detected type and,
when something is missing, what will be downloaded. Downloads are agreed once per machine (setting `install`:
`ask`, `auto`, `never`); the project type once per project (`ai/ready-check/settings.json`).

- Yes: `ready-check.py consent yes` records both and installs in the foreground, one line per component, ending
  with `Ready Check is ready: …` or `Ready Check setup incomplete: …`. If the agent cannot run commands, the user
  runs the shown command (in Claude Code by typing `!` before it).
- No: `consent no` sets `install` to `never`. Nothing is downloaded and the question is not repeated; review,
  reminders and task records keep working, and a check offers the install once when it needs a missing tool.
- A stopped DDEV/Compose runner is not started: the browser installs now, the profile checkers at the first
  static check. An unsupported stack gets only the browser.
- With `install` = `auto`, later updates (for example after a plugin update) run in the chat without a question.

Manual paths stay available through the `setup` skill: `/ready:setup` (Claude Code), `/setup` (Cursor),
`$setup` (Codex).

## Hooks

| Client | Registration | Events |
| --- | --- | --- |
| Claude Code | `hooks/hooks.json` | `SessionStart`, `UserPromptSubmit`, `Stop` |
| Cursor | `hooks/cursor-hooks.json` | `sessionStart`, `beforeSubmitPrompt` |
| Codex | `hooks/codex-hooks.json` | `SessionStart`, `UserPromptSubmit`, `Stop` |

- Session start: injects the rule "offer Ready Check after a finished task", the browser-tool status and the
  first-run question. It never installs anything and finishes in about a second.
- Prompt submit: appends the prompt to `ai/ready-check/tasks/<branch>/<date>.jsonl` (see below).
- Stop: after files changed in the session, reminds the agent once per change set to offer the check; quiet
  again after a check reaches a result. Cursor has no stop hook because its only option posts a visible message
  as the user; there the session-start rule applies.
- Hooks always exit 0 and log errors to `<data root>/logs/hooks-YYYY-MM-DD.log`.
- Codex requires a one-time trust step for plugin hooks in `/hooks`. Codex runs hook commands through
  `$SHELL -lc` with `PLUGIN_ROOT` set, so they do not run under native Windows `cmd.exe`.
- Commands call `python3`, then `python` if `python3` is missing.

No project instruction files (`AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md`) and no project MCP configs are written.

## Settings

`ready-check.py config get [key] [--project <app>]` and `config set <key> <value> [--project <app>]`.
User settings live in `<data root>/settings.json`, project overrides in `ai/ready-check/settings.json` (git-excluded).

| Key | Values | Scope |
| --- | --- | --- |
| `browser` | `ask` (default), `visible`, `background` | user, project |
| `install` | `ask` (default), `auto`, `never` | user |
| `captureTasks` | `true` (default), `false` | user, project |
| `remind` | `true` (default), `false` | user, project |
| `artifactLanguage` | `English` (default) or another language name, for example `Ukrainian`; language of reports, QA plans and handoffs (PR drafts and the report's key lines stay English) | user, project |
| `profile`, `runner`, `application` | confirmed project type | project |

## Coding rules

Rules are merged from the Claude Code `userConfig` option `rules` (exported as `CLAUDE_PLUGIN_OPTION_RULES`), the
environment variable `READY_CHECK_RULES` (the Cursor plugin variable; one rule per line), the user file
`<data root>/rules.md` and the project file `ai/ready-check/rules.md`. Files hold one rule per
line (a leading `- ` is optional; `#` lines are ignored). A `MUST:` prefix makes a broken rule block the review.
Duplicates are dropped and the injected text is capped at 4 KB. Manage them with
`ready-check.py rules list|add|remove [text] [--project <app>] [--must]` (`--project` targets the project file) or
the general `customize` command below.
How Cursor passes plugin variables to hooks is not verified yet.

## Customization, feedback and reflect

| Command | Purpose |
| --- | --- |
| `customize list\|add\|disable\|enable\|remove [text] --kind rule\|review\|qa --scope project\|global [--profile id] [--section name] [--project app] [--must]` | Rules and checklist extensions; files under `<data root>` (global) or `ai/ready-check/` (project); disabled items in `disabled.json` |
| `reports --project app [--task title]` | Per-task report folder `ai/ready-check/reports/<branch>/<task_id>/`; without `--task` the newest task on the branch |
| `summary --project app --task id --round n --verdict v --static s --review s --qa s [--finding …] [--qa-case …]` | Appends one round to the task's `summary.json` with HEAD and code fingerprint |
| `feedback add\|list --project app [--task id\|unknown] --returned yes\|no [--by …] [--reason …] [--missed yes\|no\|unknown] [--area …]` | One JSON line per record in `ai/ready-check/feedback.jsonl`; exit 3 with recent tasks when the task is unclear |
| `reflect-collect --project app [--tasks 10] [--html]` | Digest and statistics of the newest tasks; `--html` writes `ai/ready-check/reflect/overview-<date>.html` with inlined Chart.js (tables without the browser bundle) |

The browser bundle pins `chart.js` next to `axe-core`. A plugin update that changes pinned tools makes the installed
bundle outdated: with `install` = `auto` the next session reinstalls it in the chat; otherwise run the `setup` skill. `uninstall` keeps rules, extensions and `disabled.json` unless
`--custom` is given; `--reports` also removes feedback and reflect output.

## Task records

Each prompt is appended as one JSON line `{ts, client, session, branch, head, prompt}`. Prompts longer than
20 KB (UTF-8) are cut, files older than 30 days are removed on session start, and nothing is redacted: the files
are local and git-excluded. `ready-check.py tasks --project <app>` lists recent prompts by session; `check` uses
them when the task is not in the chat. Turn off with `config set captureTasks false`.

## Terminal entry point

For manual diagnostics or automation, use the installed plugin's absolute path and selected application:

```sh
python3 /path/to/ready-check/scripts/ready-check.py setup --project /path/to/application --profile drupal --dry-run
python3 /path/to/ready-check/scripts/ready-check.py setup --project /path/to/application --profile drupal
```

On Windows PowerShell, replace `python3` with `py -3` (or `python`) and quote native paths:

```powershell
py -3 "C:\Tools\ready-check\scripts\ready-check.py" setup --project "C:\Projects\My Drupal" --dry-run
```

`--component browser` prepares Playwright CLI, official MCP and the browser; `--component profile` prepares only
the selected profile's tools. The default is `all`. `--browser chromium|firefox|webkit` selects the browser (default Chromium).

`--timeout 900` controls each installation command's timeout in seconds. Setup prints JSON and returns
exit `0` for `PASS` or dry-run `PLANNED`, and `2` for `INCOMPLETE`. With multiple components, successful
ones remain installed even if another fails. Review the component results and log path before retrying.

Dry-run performs scope/path discovery but does not install or create data directories. For a container
runner it may need an available runner to determine its data path. Setup does not start containers.

## Storage and repeatability

Host defaults are `%LOCALAPPDATA%\ReadyCheck` on Windows, `~/Library/Application Support/ReadyCheck`
on macOS, and `$XDG_DATA_HOME/ready-check` or `~/.local/share/ready-check` on Linux/WSL.
Use `READY_CHECK_DATA_DIR` to select a different persistent location. `--data-dir` overrides it
for that setup invocation; use the same environment setting for later checks and the Playwright wrapper.
No shell configuration or PATH is changed automatically.

The data root and each versioned bundle carry `.ready-check-owned.json` ownership markers. Setup refuses
nonempty unowned directories, a different owner, redirects through managed paths, and links escaping the
owned tree before package managers can overwrite anything. An unclaimed data root may already hold
`settings.json`, `logs/` and `state/` written by the hooks. An owned interrupted installation can be retried without
`ready.json`; an unrecognized directory needs inspection or a separate empty Ready Check data directory.
Preview performs the same checks without claiming directories. Unrelated sibling toolkits remain separate.

Composer and npm run inside Ready Check's bundles with scoped homes/caches. Inherited Composer manifest,
vendor and binary-directory overrides, npm prefix overrides and Node preload settings are removed from the
installation subprocess; browser downloads use Ready Check's cache. Setup does not rewrite client plugin
registries, global skills, shell PATH, or project dependencies. Native marketplace commands manage client
registries; coexistence is checked separately from managed dependency preparation.

The browser and profile bundles live in directories named from the packaged manifests, lock files, and
default configuration hash. Both direct and transitive dependency versions are locked. A successful setup
writes `ready.json` last. A compatible existing installation is reused and probed again; no update commands
are run. Interrupted installations have no ready marker and can be retried. On Unix, setup can recover a
lock whose recorded process on the same host no longer exists. A live process never loses its lock merely
because a command timeout elapsed. Old ownerless legacy locks can be recovered after `timeout + 600`
seconds; locks with an unknown process state (including Windows or another host) need inspection.
Remove such a lock only after establishing that no setup still uses it.

Setup uses `npm ci --ignore-scripts` and Composer `install --no-plugins --no-scripts`. The standalone PHPCS
installation gets its own Drupal/Slevomat/VariableAnalysis registration without running a Composer plugin.
Logs and package-manager caches stay under the managed data root. Old bundle directories are retained;
there is no automatic pruning or uninstall of unrelated dependencies.

Native plugin uninstall does not remove the data root, runner-side tools, reports or task records. Use the
`uninstall` skill (`/ready:uninstall`, `/uninstall`, `$uninstall`) or
`ready-check.py uninstall --project <app> [--reports] [--data] [--dry-run]`: it previews first, removes project
settings, hook state and temporary files, keeps reports and task records unless `--reports` is given, and removes
the owned data root and the project's runner-side checkers only with `--data`.

## Browser component

Requires host Node.js 20+ and npm, and an OS supported by the pinned Playwright browser release
([system requirements](https://playwright.dev/docs/intro#system-requirements)). Setup installs pinned `@playwright/cli`, `@playwright/mcp` and `axe-core`, downloads the selected
Playwright browser revision into the managed browser cache, then launches it headlessly against an in-memory
test page. A CLI version check alone does not produce `PASS`. Missing OS libraries or sandbox permissions
remain explicit setup failures; the script does not invoke `sudo`, install OS packages, or weaken launch settings.

Use the managed CLI from the reports directory (`<repo>/ai/ready-check/reports/<branch-slug>/`):

```sh
python3 /path/to/ready-check/scripts/ready-check.py playwright --version
python3 /path/to/ready-check/scripts/ready-check.py playwright -s=ready-check-run open http://localhost:8080
```

The wrapper selects the matching installed bundle and browser cache. It does not install anything and
does not change the working directory, so QA artifacts can stay beside the report. Supply the QA run's
explicit config for a browser/viewport different from the CLI defaults. Existing CLI installations remain
usable for background mode. Visible mode uses the official MCP that ships with the plugin.
The locked versions share one Playwright/browser revision; package validation rejects mismatched revisions.

The plugin declares the MCP server `ready-playwright` for every client (`.mcp.json` for Claude Code,
`mcpServers` in the Cursor and Codex manifests). The client starts `node <plugin>/scripts/mcp.mjs`, which runs
`scripts/ready-check.py mcp` with `python3` or `python`. The server is headed, uses the installed bundle and an
isolated context, and writes artifacts to the git-excluded `ai/ready-check/tmp/playwright-mcp/`. Without
installed tools it exits with a message naming the install command. For diagnostics:

```sh
python3 /path/to/ready-check/scripts/ready-check.py mcp --project /path/to/application --headless
```

See [official MCP configuration](https://github.com/microsoft/playwright-mcp/tree/v0.0.84#configuration).

## Drupal component

The managed bundle currently targets installed Drupal 10/11 with runner PHP 8.2+ and Node.js 20+.
Drupal 11 requires at least PHP 8.3; a higher `MINIMUM_PHP` in installed core is also enforced.
Composer, npm, and required PHP extensions must already be available in that runner. Actual
platform requirements are checked after Composer install. Project-only checks can still use their own
compatible tools on other runtimes; incompatible or unknown targets cannot use the managed fallback.
A standalone module/theme needs an identified Drupal host site for managed tools that require its runtime.

Setup uses the same `LINT_RUNNER`, confirmed project settings, `.ready-check.json` and local/DDEV/Compose detection as the doctor.
`LINT_SERVICE` and `LINT_CONTAINER_ROOT` select the existing Compose service/application mount. It never
silently changes runner or rewrites mounts/configuration.

For local checks, profile data uses the host data root. In a container it defaults to that runner user's
`$XDG_DATA_HOME/ready-check` or `~/.local/share/ready-check`; for DDEV it defaults to `/mnt/ddev-global-cache/ready-check`
when the parent cache directory exists and is writable. Setup creates its own subdirectory on the first
install. Otherwise it falls back to the home directory. Set `READY_CHECK_RUNNER_DATA_DIR` (or
`--runner-data-dir` for setup) to an external path visible and writable in that runner. Keep it outside the
application repository and installed plugin. Files are transferred through the runner's stdin; no new mount
or project dependency directory is needed. Container data lasts only as long as its filesystem/volume;
rerun setup after a container recreation if it was not stored persistently. Data paths must be absolute;
spaces and Unicode are supported. Container data paths use POSIX syntax on every host OS.

The bundle includes Drupal Coder/PHPCS, PHPStan with phpstan-drupal and deprecation rules, Twig CS Fixer,
Symfony YAML, PHPMD, ESLint, Stylelint with SCSS support, and jscpd. Dead-code analysis stays opt-in and its
additional extension is not included. Default JS rules use ESLint recommended rules, browser globals, and
Drupal globals; default styles use standard SCSS rules. These are visible baseline defaults, not a claim
that every project's frontend conventions are identical.

Each checker first selects its existing project tool; an explicitly configured shared tool remains available
where supported, then a missing tool can use the installed profile bundle. Existing project configuration
takes priority independently of the executable source. Missing JS/style config can use profile defaults
after setup. Existing ambiguous/broken config, a nonexecutable binary, or a crashed checker never triggers
a weaker fallback. Missing project plugins/autoloaders can still require project preparation; the bundle
does not replace the Drupal application's runtime dependencies.

Doctor/static JSON records selected paths, sources, actual executable versions, and configuration identity.
These enter the scope snapshot, so changes to effective tools/settings invalidate an earlier result.
Doctor and static never install. When `install` is `auto`, the `check` skill installs a missing profile bundle in the chat before rerunning them.

## Laravel, Symfony, Python and Go components

| Profile | Installer | Bundle | Runner needs |
| --- | --- | --- | --- |
| `laravel` | `composer install` from the pinned lock, then `npm ci` | Pint, PHPStan with Larastan, Rector, PHPMD, ESLint, Stylelint, jscpd | PHP 8.2+, Composer, Node.js 20+ |
| `symfony` | `composer install` from the pinned lock, then `npm ci` | PHP-CS-Fixer, PHPCS, PHPStan with phpstan-symfony and phpstan-doctrine, PHPMD, ESLint, Stylelint, jscpd | PHP 8.2+, Composer, Node.js 20+ |
| `python` | `python -m venv --copies`, `pip install --require-hashes --no-deps` from the hash-pinned `requirements.txt`, `pip check`, then `npm ci` | Ruff, mypy, Bandit, pip-audit, ESLint, Stylelint, jscpd | Python 3.10+, Node.js 20+ |
| `go` | `go install <module>@<version>` with `GOTOOLCHAIN=local`, verified against the Go checksum database and the pinned `h1:` sums, then `npm ci` | golangci-lint v2, govulncheck, ESLint, Stylelint, jscpd | Go 1.26+, Node.js 20+ |

Runner selection and data directories work as for Drupal. Compose defaults: Laravel `laravel.test` and
`/var/www/html` (Sail); Symfony `php` and `/app`; Python `web`, `app` or `django` and `/app`; Go `app`, `api` or
`go` and `/app`. Python checks run with the project interpreter (`READY_CHECK_PYTHON`, `.venv`, `venv`,
`uv run`, `poetry run`, then `python3`); project tools in the venv win over the bundle. Go never downloads a
newer toolchain: an older runner Go makes managed tools `INCOMPLETE`. A project golangci-lint v1 config needs
the project's own v1 binary.

## Adding another profile

Set `scripts.setup` in the new profile manifest to a Python file inside that profile. It exposes
`setup(project, host_root, runner_data_dir, dry_run, timeout)` and returns a dictionary with `component`
equal to the profile ID and `status` of `PASS`/`INCOMPLETE`, or `PLANNED`/`INCOMPLETE` for dry-run. Include
the selected runner, dependency directory, versions, and reuse details. Dry-run performs no writes.
The entry point owns its framework's compatibility, assets, runner installation, and prerequisite checks;
the shared dispatcher handles component selection and browser setup without importing a framework directly.
Language-neutral parts (scope, changed lines, runner, dispatcher, managed bundles) live in
`profiles/_shared/core`, PHP checks in `profiles/_shared/php`; a profile declares its providers and extra
checks in `scripts/spec.py`. The validator's per-profile table lists the files and pins it requires.

References: [Drupal PHP requirements](https://www.drupal.org/docs/getting-started/system-requirements/php-requirements),
[Composer lock installation](https://getcomposer.org/doc/01-basic-usage.md#installing-dependencies),
[Playwright CLI](https://github.com/microsoft/playwright-cli).
