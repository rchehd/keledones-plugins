# Go QA guidance

Apply this guidance to affected RCs and code paths. Use the runner and deployment process found in the project; do not
introduce new requirements merely because this is Go.

## Establish the local app

- Resolve the service address and start command (`go run .`, a built binary, `air`, Docker Compose) from the project
  files. Check that the running process serves the working copy (rebuilt after the change); a Git HEAD or a port that
  answers is not enough.
- Read configuration only for the facts QA needs (listen address, database kind). Never copy secrets into the report.

## Resolve required preparation

Determine whether the changed path needs a schema migration, seed data or an extra service. Inspect the project's own
process. Report missing preparation and obtain the decision instead of silently running migrations or seeds. Record
the commands executed when preparation is authorized, then recheck that the service runs the current build.

## Test user and login

The service's own HTTP endpoints are the test surface: use the browser for pages and `curl` or the HTTP client for the
API. When the service has accounts, create a test user through its own sign-up, seed command or admin endpoint when the
approved plan covers test data. Keep credentials and tokens only in `ai/ready-check/qa-accounts.json` (local, never
committed, never in the report) and list the user as test data. Never use real accounts or production databases.

## QA checklist by change type

Use the change types from the [review checklist](review.md#change-type-map).

**HTTP handlers**
- [ ] Valid request returns the expected status and body; repeat it after a restart to confirm persistence.
- [ ] Empty, missing, oversized and wrongly typed parameters give a clean 4xx, never a 500 or a hang (equivalence classes).
- [ ] Wrong method, wrong content type and malformed JSON are refused with the right status.
- [ ] Extra JSON fields (`id`, `role`, `owner`) do not change protected attributes (error guessing).

**Access**
- [ ] Intended caller succeeds; a lower role, another user's record and an anonymous caller are refused (decision table).
- [ ] A direct URL and a changed id are refused server-side.

**Search and queries**
- [ ] `'`, `"`, `%`, `_` and SQL fragments in a query parameter return results or an empty list, never an error (error guessing).

**Concurrency and shutdown**
- [ ] Parallel requests (`xargs -P` or a short loop) return consistent results; no panic in the log.
- [ ] A slow or cancelled client does not leave the request running; the service stops cleanly on SIGTERM.

**Templates and responses**
- [ ] `<b>x</b>` and quotes in user data render as text; JSON responses keep the documented shape and content type.

## Familiar Go problems (error guessing)

- SQL built with `+` or `fmt.Sprintf`; `'` in the search box breaks the page or leaks rows.
- An ignored error (`Encode`, `Write`, `Close`) hides a failed response or a half-written file.
- A request without a size or length limit lets one client exhaust memory.
- A debug `log.Printf("DEBUG ...")` or `spew.Dump` writes user input to the production log.
- A goroutine started per request without cancellation keeps running after the client left.
- A map shared between handlers without a mutex panics under load ("concurrent map writes").
- A handler without a check works for the owner but also for any other caller.
- Works with SQLite but fails on PostgreSQL (placeholders `?` vs `$1`, case-sensitive `LIKE`).

Verify persistence by reopening the record through the service or a read-only query. Track created users and rows with
IDs and reasons; list data left behind and any cleanup that still needs a decision.
