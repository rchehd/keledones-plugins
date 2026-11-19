# Laravel static checks

Run the Python profile dispatcher from the installed plugin. Python 3.9+ and Git are required on Linux,
macOS, native Windows, and WSL. The examples use `python3`; on Windows PowerShell use `py -3`.

```sh
python3 /path/to/ready-check/scripts/ready-check.py doctor --profile laravel --project /path/to/application --base main --output /path/to/repository/.ai/ready-check/reports/<branch-slug>/doctor.json
python3 /path/to/ready-check/scripts/ready-check.py static --profile laravel --project /path/to/application --base main --output /path/to/repository/.ai/ready-check/reports/<branch-slug>/static.json
```

Get the directory with `ready-check.py reports --project <app>`. Both commands take exactly one of `--base <ref>` or
`--commits <sha> [<sha> ...]`; `main` is illustrative. Commits mode checks only the named task commits plus
uncommitted changes inside those commits' files; other uncommitted changes are listed as
`uncommitted_outside_task`. The application may be a subdirectory of a repository. Uncovered changes outside
the application stay visible in the task report.

## Runner and dependencies

`LINT_RUNNER`, the application's `.ready-check.json` `runner` field, or project markers select `local`,
`ddev`, or `compose`, in that order. A DDEV marker takes precedence over Compose detection. An unavailable
selected environment produces `INCOMPLETE`; the dispatcher does not silently fall back to a different PHP.

Compose defaults to service `laravel.test` (Sail), then `app`, then `php`, with container root `/var/www/html`.
Set `LINT_SERVICE` and `LINT_CONTAINER_ROOT` for another layout. DDEV uses the same container-root override and
keeps managed tools in `/mnt/ddev-global-cache/ready-check`.

Project `vendor/bin` tools take priority; Pint, Rector and PHPStan fall back to the managed bundle (see
[dependency setup](../../dependencies/SETUP.md)). A broken project executable or config never triggers fallback.
Pint reads the project's `pint.json` (otherwise the `laravel` preset); Rector reads `rector.php` (otherwise the
Laravel code-quality set); PHPStan reads `phpstan.neon` or `phpstan.neon.dist` in the project root (otherwise
Larastan at level 5). The managed PHPStan needs the project's `vendor/autoload.php` inside the runner.

## Checks

Required when their inputs apply: Pint (`--test`, changed PHP files, file-level findings because Pint reports
no lines), PHPStan with Larastan, PHP and YAML syntax (Blade templates are not parsed as PHP), debug leftovers
(`dd(`, `dump(`, `ray(`, `var_dump(`, `print_r(` in PHP, Blade and JavaScript), diff formatting, ESLint/Stylelint,
and `composer validate`. Advisory: Rector `--dry-run` (file-level), PHPMD, `composer audit` and jscpd.
`vendor`, `node_modules`, `storage`, `bootstrap/cache` and `public/build` are excluded. Statuses, exit codes and
the stage gate are identical to the other profiles: only `can_proceed: true` opens the next stage, and a later
fix needs a fresh run. PHPStan and the other tools analyse only the changed files, so unchanged callers are
traced in review.
