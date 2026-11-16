# Go review checklist

Apply the general `review` workflow with this checklist. Review only what the change touches:

1. Classify every changed path (and new, deleted or renamed file) into change types using the map below.
2. Run section A always. Run every other section whose trigger matches at least one change type.
3. Check each item of a triggered section against the current code and record it as `CHECKED`, `FINDING`,
   `INCOMPLETE` or `N/A` with a one-line reason. List the untriggered sections once, each with the reason.
4. The review passes when every triggered item is `CHECKED`, `N/A` with a reason, or a nonblocking note. A `FINDING`
   blocks only when it is a demonstrated defect: a security hole, a data race, a leak, a regression or an API that does
   not exist in the installed versions. Style preferences stay advisory.

The user's and team's extra items (`customize list --kind review`) join the matching sections below.

## Change-type map

| Change type | Typical paths and signals | Sections |
| --- | --- | --- |
| Go code | `**/*.go` | A, B |
| Error paths | `err`, `errors.`, `fmt.Errorf`, `panic(`, `recover()` | B |
| Calls with deadlines | `context.`, `http.Client`, `time.After`, `Timeout`, `ctx` parameters | C |
| Concurrency | `go func`, `sync.`, `chan`, `errgroup`, shared maps and slices | D |
| Resources | `Open`, `Close`, `defer`, `Body`, `sql.Rows`, `os.File` | E |
| Database access | `database/sql`, `Query`, `Exec`, `sqlx`, `gorm`, SQL strings | F |
| HTTP handlers and routes | `http.Handler`, `HandleFunc`, `mux.`, `gin.`, `chi.`, `r.URL`, `r.Body` | G |
| Package layout and API | new packages, `internal/`, exported names, interfaces, `init()` | H |
| Dependencies | `go.mod`, `go.sum`, `vendor/` | A, I |

## A. Versions and APIs (always)

- [ ] Go version and module versions recorded from `go.mod`, `go.sum` and the toolchain, not from ranges or memory.
- [ ] Changed code uses no API deprecated or removed in the installed Go and dependency versions (`staticcheck` SA1019 or release notes when unsure).
- [ ] No `spew.Dump`, `pp.Println`, `println(` or `log.Printf("DEBUG ...")` calls remain; logging goes through the project's logger.

## B. Error handling

- [ ] Every returned error is checked or deliberately discarded with a stated reason (`_ =`); unchecked `Encode`, `Write` and `Close` results are not left silent.
- [ ] Errors are wrapped with context (`fmt.Errorf("...: %w", err)`) and compared with `errors.Is`/`errors.As`, not by string.
- [ ] `panic` is not used for expected failures; `recover` sits at a boundary (server, goroutine) and logs.
- [ ] A function never returns both a usable value and a non-nil error unless documented; callers check the error first.
- [ ] Errors shown to clients do not leak internals (SQL text, file paths, stack traces); the detail goes to the log.

## C. Context and timeouts

- [ ] Functions that block, call the network or query the database take a `context.Context` as the first parameter and pass it on (`QueryContext`, `NewRequestWithContext`).
- [ ] Outgoing HTTP clients and servers set timeouts (`http.Client.Timeout`, `ReadHeaderTimeout`); no `http.DefaultClient` for untrusted or slow peers.
- [ ] `context.WithTimeout`/`WithCancel` results call `cancel` (usually `defer cancel()`); a context is never stored in a struct for later requests.
- [ ] `time.After` in loops is replaced by a reusable timer; sleeping loops honor `ctx.Done()`.

## D. Goroutines and data races

- [ ] Every started goroutine has a defined end (context, closed channel, `WaitGroup`/`errgroup`); no goroutine per request without cancellation.
- [ ] Shared maps, slices and structs are guarded (`sync.Mutex`, channels, `atomic`); handlers do not mutate package-level state without a lock.
- [ ] Loop variables captured by closures behave as intended for the module's Go version; results are not written from several goroutines to one slice index without ownership.
- [ ] Channels have one clear closer; sends cannot block forever after the receiver is gone.
- [ ] The change was run or can be run with `go test -race`; races are reported as findings.

## E. Resource closing

- [ ] `resp.Body`, `sql.Rows`, files, listeners and tickers are closed on every path, with `defer` after the error check.
- [ ] `rows.Err()` is checked after iterating `sql.Rows`; transactions end with `Commit` or a deferred `Rollback`.
- [ ] Request bodies are bounded (`http.MaxBytesReader`, `io.LimitReader`) before they are read into memory.
- [ ] `defer` inside loops is not used for resources that must close per iteration.

## F. Database access

- [ ] Queries use placeholders and bound arguments; no user input is joined into SQL with `+`, `fmt.Sprintf` or `strings.Builder` (gosec G201/G202).
- [ ] Dynamic identifiers (column, order) come from an allow-list, not from the request.
- [ ] Context-aware calls are used; connection pool limits and timeouts are intentional.
- [ ] Multi-step writes that must succeed together run in one transaction; migrations are reversible or state why not.
- [ ] `LIKE` patterns escape `%` and `_` when the user's text is meant literally.

## G. HTTP handlers, validation and authorization

- [ ] Every new or changed handler checks authentication and authorization before acting; objects are looked up scoped to the caller.
- [ ] Method and content type are enforced; state changes never answer to GET.
- [ ] Request input (query, path, headers, JSON body) is validated for presence, type, length and range before use; unknown or extra JSON fields cannot set protected attributes (`DisallowUnknownFields`, separate input structs).
- [ ] Responses set the right status and `Content-Type`; error paths return after writing the response.
- [ ] HTML output uses `html/template`, not `text/template`; redirects built from input are validated.
- [ ] CORS, cookies (`Secure`, `HttpOnly`, `SameSite`) and CSRF protection stay intentional.

## H. Package boundaries and API

- [ ] Packages keep one purpose; no import cycles or reaching into another package's internals (`internal/` respected).
- [ ] New exported names are needed by other packages and documented; interfaces are small and defined where they are used.
- [ ] No new `init()` side effects or mutable package-level globals shared across requests.
- [ ] Callers and implementations of changed signatures are updated, including unchanged files that static checks do not cover.

## I. Dependencies

- [ ] New or updated modules are compatible with the installed Go version; licenses and maintenance checked; `go.sum` committed.
- [ ] `govulncheck` output, when available, is reviewed as advisory evidence; a called vulnerability is a finding when a fixed version exists.

## Hand-off to QA

- [ ] Items the code cannot settle (limits in effect, behavior under load, configuration per environment) become
      concrete planned QA checks.
- [ ] No migrations, seeds or destructive commands were run during review.

References: [Effective Go](https://go.dev/doc/effective_go), [Go Code Review Comments](https://go.dev/wiki/CodeReviewComments),
[gosec rules](https://github.com/securego/gosec#available-rules), [staticcheck checks](https://staticcheck.dev/docs/checks/),
[golangci-lint linters](https://golangci-lint.run/docs/linters/), [govulncheck](https://go.dev/doc/security/vuln/).
