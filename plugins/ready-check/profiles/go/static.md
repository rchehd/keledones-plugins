# Go static checks

Run the Go profile dispatcher from the installed plugin. Python 3.9+ and Git are required on Linux, macOS, native
Windows, and WSL. The examples use `python3`; on Windows PowerShell use `py -3`.

```sh
python3 /path/to/ready-check/scripts/ready-check.py doctor --profile go --project /path/to/application --base main --output /path/to/repository/.ai/ready-check/reports/<branch-slug>/doctor.json
python3 /path/to/ready-check/scripts/ready-check.py static --profile go --project /path/to/application --base main --output /path/to/repository/.ai/ready-check/reports/<branch-slug>/static.json
```

Get the directory with `ready-check.py reports --project <app>`. Both commands take exactly one of `--base <ref>` or
`--commits <sha> [<sha> ...]`; `main` is illustrative. Commits mode checks only the named task commits plus
uncommitted changes inside those commits' files; other uncommitted changes are listed as
`uncommitted_outside_task`. The application root is the folder with `go.mod`.

## Runner and tools

`LINT_RUNNER`, the application's `.ready-check.json` `runner` field, or project markers select `local`, `ddev` or
`compose`. Compose defaults to service `app`, then `api`, then `go`, with container root `/app` (override with
`LINT_CONTAINER_ROOT` or `container_root`, `LINT_SERVICE` or `service`). An unavailable runner produces `INCOMPLETE`.

`go` and `gofmt` come from the runner (`gofmt` from `$(go env GOROOT)/bin`, then `PATH`). golangci-lint and govulncheck
come from `PATH` or `$(go env GOBIN)`/`$(go env GOPATH)/bin` first (source `project`) and from the managed bundle (see
[dependency setup](../../dependencies/SETUP.md)) otherwise; a broken existing executable never triggers fallback.
Checks never write into the project: `go build` discards its output and Go's own caches stay at their defaults.

## Checks

Required when their inputs apply:

- `gofmt -d` on changed `.go` files (file-level finding at the first differing line; syntax errors are findings).
- `go vet` on the packages of changed files; findings on changed lines. Type errors reported by vet fail the check on
  any line.
- golangci-lint on the packages of changed files with a project `.golangci.yml|yaml|toml|json` when present, otherwise
  the managed default (`version: "2"`: `errcheck`, `govet`, `gosec`, `ineffassign`, `staticcheck`, `unused`). Findings
  are limited to changed lines, the linter name is the finding source, and package type errors fail the check. A project
  config in the golangci-lint v1 format needs the project's own v1 binary on `PATH`.
- `go build -o /dev/null ./...` (compile errors anywhere in the module fail).
- Debug leftovers (`spew.Dump`/`spew.Printf`, `pp.Print`/`pp.Println`, `log`/`fmt` print calls starting with
  `"DEBUG`, builtin `println(`; ignored in `_test.go` files), diff formatting, ESLint/Stylelint.

Advisory: `govulncheck -json ./...` when `.go`, `go.mod` or `go.sum` changed (called vulnerabilities are warnings; a
vulnerability database that cannot be reached is `INCOMPLETE`) and jscpd. `vendor`, `node_modules`, `testdata` and
`.git` are excluded. Statuses, exit codes and the stage gate are identical to the other profiles: only
`can_proceed: true` opens the next stage, and a later fix needs a fresh run. Tools analyse the changed packages, so
unchanged callers are traced in review.
