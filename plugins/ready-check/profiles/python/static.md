# Python static checks

Run the Python profile dispatcher from the installed plugin. Python 3.9+ and Git are required on Linux,
macOS, native Windows, and WSL. The examples use `python3`; on Windows PowerShell use `py -3`.

```sh
python3 /path/to/ready-check/scripts/ready-check.py doctor --profile python --project /path/to/application --base main --output /path/to/repository/ai/ready-check/reports/<branch-slug>/doctor.json
python3 /path/to/ready-check/scripts/ready-check.py static --profile python --project /path/to/application --base main --output /path/to/repository/ai/ready-check/reports/<branch-slug>/static.json
```

Get the directory with `ready-check.py reports --project <app>`. Both commands take exactly one of `--base <ref>` or
`--commits <sha> [<sha> ...]`; `main` is illustrative. Commits mode checks only the named task commits plus
uncommitted changes inside those commits' files; other uncommitted changes are listed as
`uncommitted_outside_task`. The application may be a subdirectory of a repository.

## Runner and interpreter

`LINT_RUNNER`, the application's `.ready-check.json` `runner` field, or project markers select `local`, `ddev` or
`compose`. Compose defaults to service `web`, then `app`, then `django`, with container root `/app` (override with
`LINT_CONTAINER_ROOT` or `container_root`, `LINT_SERVICE` or `service`). An unavailable runner produces `INCOMPLETE`.

The project interpreter is resolved in order: `READY_CHECK_PYTHON`, `<root>/.venv/bin/python`,
`<root>/venv/bin/python`, `uv run --no-sync python` (with `uv.lock`), `poetry run python`, then the runner's
`python3`. Ruff, mypy, Bandit and pip-audit come from the project venv first and from the managed bundle (see
[dependency setup](../../dependencies/SETUP.md)) otherwise; a broken project executable never triggers fallback.

## Checks

Required when their inputs apply:

- `ruff check` on changed Python files (project `[tool.ruff]`, `ruff.toml` or `.ruff.toml` wins; otherwise the managed
  default `E4, E7, E9, F, B`). Findings are limited to changed lines.
- `ruff format --check --diff` (file-level finding at the first differing line).
- Python syntax (`ast` compile with the project interpreter), debug leftovers (`breakpoint()`, `pdb`/`ipdb`
  `set_trace`, and `print(` outside `tests/`, `test_*.py` and `management/commands/`), diff formatting, ESLint/Stylelint.
- mypy only when the project configures it (`[tool.mypy]`, `mypy.ini`, `setup.cfg`); otherwise `N/A`.
- Django only: `manage.py check` (errors fail, warnings are findings) and `makemigrations --check --dry-run` (fails
  when model changes have no migration). A project that cannot boot (import or settings error) is `INCOMPLETE`, never
  `PASS`. Both are `N/A` without `manage.py`.

Advisory: Bandit (`HIGH` is an error finding, the rest warnings), `pip-audit` on changed requirements files and
jscpd. `.venv`, `venv`, `__pycache__`, `.tox`, `node_modules`, `build` and `dist` are excluded; `migrations` are
included unless the project's Ruff config excludes them. Statuses, exit codes and the stage gate are identical to the
other profiles: only `can_proceed: true` opens the next stage, and a later fix needs a fresh run. Tools analyse only
the changed files, so unchanged callers are traced in review.
