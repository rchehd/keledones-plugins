# Drupal static checks

Run the Python profile dispatcher from the installed plugin. Python 3.9+ and Git are required on Linux,
macOS, native Windows, and WSL. Bash, executable mode preservation, and GNU grep are not required.
The examples use `python3`; on Windows PowerShell use `py -3` (or an available Python 3 interpreter).

```sh
python3 /path/to/ready-check/scripts/ready-check.py doctor --profile drupal --project /path/to/application --base main --output /path/to/repository/.ai/ready-check/reports/<branch-slug>/doctor.json
python3 /path/to/ready-check/scripts/ready-check.py static --profile drupal --project /path/to/application --base main --output /path/to/repository/.ai/ready-check/reports/<branch-slug>/static.json
```

Get the directory with `ready-check.py reports --project <app>`. Both commands take exactly one of `--base <ref>` or
`--commits <sha> [<sha> ...]`. Use the application and scope already resolved with the user; `main` is illustrative.
Commits mode checks only the named task commits (non-contiguous allowed; other people's commits between them are
ignored) plus uncommitted changes inside those commits' files, with line ownership from git blame; other uncommitted
changes are listed as `uncommitted_outside_task`. The application may be a subdirectory of a repository.
The result includes uncovered changes outside that application; they must remain visible in the task report.

## Runner and dependencies

`LINT_RUNNER`, the application's `.ready-check.json` `runner` field, or project markers select `local`,
`ddev`, or `compose`, in that order. A DDEV marker takes precedence over Compose detection. An unavailable
selected environment produces `INCOMPLETE`; the dispatcher does not silently fall back to a different PHP.

For DDEV, managed tools default to `/mnt/ddev-global-cache/ready-check` (persistent volume), falling back to the home directory.
Compose uses service `php` and container root `/var/www/html` by default. Set `LINT_SERVICE` and
`LINT_CONTAINER_ROOT` for another layout. DDEV uses the same container-root override. Ask the user about
ambiguous environment settings rather than starting containers or changing their configuration.

Use project `vendor/bin` and local Node binaries beside each linter config. `LINT_PHPSTAN_TOOLS` can explicitly
point to a shared Composer-tool directory as seen by the selected runner. `LINT_JSCPD` can select a host
jscpd binary. Missing tools can use the separately installed managed profile bundle; see
[dependency setup](../../dependencies/SETUP.md). Existing project executables and configs take priority
and are used for their entire run, including when they fail. JS/style configs are looked up only from the file's directory upward (no repository-wide search); a scaffolded
config that contains only `extends` pointing exclusively to the detected Drupal core configs is ignored.
Any additional project rules/settings or non-core extends preserve the project config. Missing configs use the bundle's visible
baseline defaults after setup. PHPStan config is looked up in the project root, then `web/`, `docroot/`, `html/`, never in core. There are no personal tool-directory defaults.
Directory paths and filenames with spaces, Unicode, and shell metacharacters are passed as arguments.
Container paths remain POSIX paths even on a Windows host. Changed symlinks require a separately agreed scope.
Drupal core is excluded under every detected core path (`web/core`, `docroot/core`, `html/core`, root `core`); excluded files are listed in scope `excluded_files`.
PHPMD cannot analyse source filenames containing commas; that advisory check reports `INCOMPLETE`.

PHPCS, PHPStan, PHP/YAML syntax, debug leftovers (including `dump(`), diff formatting, Drupal module configuration, Twig,
JavaScript/styles, and Composer validation are required when their inputs apply. Duplication, PHPMD, and
dependency audit are advisory. Dead-code checking is disabled by default. The definitions live in
`profile.json`; absent advisory dependencies are visible without blocking required checks.

Without a saved static result, doctor probes tool availability and versions. Missing tools,
unavailable required defaults, unavailable runners, malformed output, and unexpected tool exits are setup or
execution problems. They never count as successful checks. Audit is an advisory Composer command and may
require network access under the current harness's permissions.

## Results and stage gate

Both commands print a JSON object. `--output` also saves it. Doctor, setup and static can exceed the harness's
default command timeout: run in the background or with the maximum timeout, wait, never kill or rerun. Each check includes `id`, `required`, `status`, `findings`, `reason`, and `evidence`. Applicable available
checks also record `tools`: executable path, source (`project`, `profile`, explicit `shared`, or `runner`),
actual version, and configuration source/identity where relevant. Static evidence lands in the report directory's `evidence/` subfolder.

Doctor JSON has top-level `status` `READY`, `MISSING` or `INCOMPLETE` (no `can_proceed`), per-check `READY`, `MISSING` or `N/A`,
and exit `0` only for `READY`. Doctor `READY` is never a static result.

Static statuses and process exit codes (static JSON keeps `can_proceed`):

| Status | Exit code | Meaning |
| --- | --- | --- |
| `PASS` | 0 | Applicable required checks completed without blocking findings |
| `N/A` | 0 | No required check applies to these changes |
| `FAIL` | 1 | At least one required check found a blocking problem |
| `INCOMPLETE` | 2 | Required checks or the scope could not be verified |

Only a static result with `can_proceed: true` opens the next stage. Keep per-check warnings and advisory
`INCOMPLETE` results in the report. `N/A` must retain its explanation. The JSON scope includes HEAD,
merge base, changed paths, and a SHA-256 snapshot covering the tracked diff and new non-ignored file contents.
Tool versions, sources, effective configurations, packaged checker scripts, and selected managed bundle
identity also enter the snapshot. Changes made during verification invalidate the result. Any later fix
requires a fresh static run. Doctor and static runs use the same tool selection and identity.

All static tools, including PHPStan, report only findings on lines that belong to the task. PHPStan analyses only the
changed PHP files, so breakage in unchanged callers is not reported; review traces it. Existing configured
baselines are respected; the checker does not generate a baseline or suppress existing errors automatically.

With managed PHPStan and the default Drupal configuration, Ready Check can retry a bootstrap fatal in two
unchanged themes whose main files contain only function declarations and imports, with optional
`declare(strict_types=...)`. Every shared function definition and its PHPDoc must match. The retry uses the
same rules and task files and scans one theme's main file for symbols without executing it during bootstrap.
It verifies that any loaded function from the skipped theme's declarations comes from the retained theme.
Both attempts are logged. The static JSON records both locations in `bootstrap_conflict` and both file hashes
after recovery in `bootstrap_recovery`. Use `doctor --static-result <static-json>` before reusing the result
to verify the hashes and repeat PHPStan analysis of the same task scope in the selected runner. The check
uses a fresh cache directory and saves the result under `bootstrap_verification`. A changed theme file,
failed analysis or changed recovery requires a new static result.
When recovery is ineligible or yields no usable report, PHPStan reports `INCOMPLETE` with the locations and log.

Ready Check can check a Drupal extension stored elsewhere in the repository when exactly one installed Drupal
application links to that directory from its profiles, modules or themes. Ready Check uses that
application's runner, Composer dependencies and tools. Git scope and findings stay relative to the
source directory. An unavailable or ambiguous link leaves the check incomplete.

The dispatcher runs the portable `scripts/lint.py` engine. Auto-fix is never enabled. Linters
may create their normal caches. Generated configs use external temporary storage for local checks;
containers use a unique bridge directory under `.ai/ready-check/tmp`, removed after that check. All its
parent components must be real directories. A run never sweeps temporary directories from other or
interrupted runs; inspect leftover directories before removing them manually.
Legacy `.ready-check-lint.*` directories in the application root stay out of the task scope.
