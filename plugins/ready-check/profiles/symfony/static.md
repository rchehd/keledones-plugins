# Symfony static checks

Run the Python profile dispatcher from the installed plugin. Python 3.9+ and Git are required on Linux,
macOS, native Windows, and WSL. The examples use `python3`; on Windows PowerShell use `py -3`.

```sh
python3 /path/to/ready-check/scripts/ready-check.py doctor --profile symfony --project /path/to/application --base main --output /path/to/repository/.ai/ready-check/reports/<branch-slug>/doctor.json
python3 /path/to/ready-check/scripts/ready-check.py static --profile symfony --project /path/to/application --base main --output /path/to/repository/.ai/ready-check/reports/<branch-slug>/static.json
```

Get the directory with `ready-check.py reports --project <app>`. Both commands take exactly one of `--base <ref>` or
`--commits <sha> [<sha> ...]`; `main` is illustrative. Commits mode checks only the named task commits plus
uncommitted changes inside those commits' files; other uncommitted changes are listed as
`uncommitted_outside_task`. The application may be a subdirectory of a repository. Uncovered changes outside
the application stay visible in the task report.

## Runner and dependencies

`LINT_RUNNER`, the application's `.ready-check.json` `runner` field, or project markers select `local`
(Symfony CLI or system PHP), `ddev`, or `compose`, in that order. A DDEV marker takes precedence over Compose
detection. An unavailable selected environment produces `INCOMPLETE`; the dispatcher does not silently fall back
to a different PHP.

Compose defaults to service `php` (symfony-docker), then `app`, with container root `/app`. The runner supports a
single root: for a layout that mounts the project elsewhere (for example `/var/www/html`) set `LINT_CONTAINER_ROOT`
or `container_root` in `.ready-check.json`, and `LINT_SERVICE` or `service` for another service name. DDEV uses
the same container-root override and keeps managed tools in `/mnt/ddev-global-cache/ready-check`.

Project `vendor/bin` tools take priority; PHPStan, PHP-CS-Fixer and PHPMD fall back to the managed bundle (see
[dependency setup](../../dependencies/SETUP.md)). A broken project executable or config never triggers fallback.
PHP-CS-Fixer reads `.php-cs-fixer.php`, then `.php-cs-fixer.dist.php` (otherwise the `@Symfony` ruleset);
PHPStan reads `phpstan.neon` or `phpstan.neon.dist` in the project root (otherwise phpstan-symfony at level 5, plus
phpstan-doctrine when `doctrine/orm` is installed). The managed PHPStan needs the project's `vendor/autoload.php`
inside the runner. The console checks run the project's own `bin/console`, so they need an installed `vendor/`
and a bootable application.

## Checks

Required when their inputs apply:

- PHP-CS-Fixer (`check --dry-run --format=json --diff`, changed PHP files; one finding per file at the first line it would
  change inside the task's lines; formatting elsewhere in the file is ignored).
- PHPStan with phpstan-symfony (and phpstan-doctrine), PHP and YAML syntax (`php -l`, `Yaml::parseFile` with custom
  tags enabled).
- `bin/console lint:container`, when PHP files or YAML under `config/` changed. Console output is not
  machine-readable: a DependencyInjection exception is a `FAIL`, any other failure to boot is `INCOMPLETE`.
- `lint:yaml` (changed YAML under `config/` and `translations/`), `lint:twig` (changed `.twig` templates) and
  `lint:xliff` (changed `.xlf`/`.xliff`), all with `--format=json`; each lists only the changed files.
- Debug leftovers (`dump(`, `dd(`, `var_dump(`, `print_r(` in PHP, Twig and JavaScript), diff formatting,
  ESLint/Stylelint, and `composer validate`.

A console check is `N/A` when its inputs did not change, and `INCOMPLETE` (never `PASS`) when `bin/console` fails
to boot or prints no usable report. Advisory: `doctrine:schema:validate --skip-sync` (mapping only, no database;
`N/A` when Doctrine ORM is not installed), PHPMD, `composer audit` and jscpd.
`vendor`, `var`, `node_modules`, `public/build` and `public/bundles` are excluded. Statuses, exit codes and
the stage gate are identical to the other profiles: only `can_proceed: true` opens the next stage, and a later
fix needs a fresh run. PHPStan and the other tools analyse only the changed files, so unchanged callers are
traced in review.
