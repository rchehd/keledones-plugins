# Laravel QA guidance

Apply this guidance to affected RCs and code paths. Use the Laravel version, runner and deployment process found
in the project; do not introduce new requirements merely because this is Laravel.

## Establish the local app

- Resolve the app URL and the runner (Sail, DDEV or local `php artisan serve`) from the project files and
  `artisan about`. Check that the running app serves the working copy, including uncommitted files and built
  Vite assets (`public/build` or the dev server). A title or Git HEAD alone does not establish this.
- Read `.env` values only for the facts QA needs (`APP_ENV`, `DB_CONNECTION`, `MAIL_MAILER`, `QUEUE_CONNECTION`,
  `CACHE_STORE`). Never copy secrets, `APP_KEY` or tokens into the report.

## Resolve required preparation

Determine whether the changed path needs a migration, seeder, `storage:link`, asset build, cache clear or an
enabled queue worker. Inspect the project's own process. Report missing preparation and obtain the decision
instead of silently running `migrate`, `db:seed`, `migrate:fresh` or `cache:clear`. Record the commands
executed and their results when preparation is authorized, then recheck the source identity and rerun affected stages.

## Test user and login

Use a test user, not an administrator, for non-admin behavior. When the approved plan covers test data, create
one through the runner, for example `php artisan tinker --execute="App\Models\User::factory()->create([...])"`
or the project's seeder. Keep the generated credentials only in `ai/ready-check/qa-accounts.json` (local, never
committed, never in the report or PR draft), use them to log in through the app's form, and list the user as test data.
Never reuse real accounts or production credentials; never create users on a shared or production database.

## QA checklist by change type

The user's and team's extra items (`customize list --kind qa`) join the matching sections and the familiar problems.
Use the change types from the [review checklist](review.md#change-type-map). Plan scenarios from the sections the
change triggers; list the others once with the reason. Each item names the technique it relies on.

**Forms and validation**
- [ ] Main submit with valid data, then reload: saved values are shown (persistence).
- [ ] Required, empty, too long and invalid values show readable errors and keep old input (equivalence classes).
- [ ] Extra request fields (`role`, `is_admin`, `id`, `created_at`) do not change protected columns (error guessing).
- [ ] Double submit, back after submit, refresh; expired session or CSRF token gives a clean error (state transitions).

**Routes, access and policies**
- [ ] Intended role succeeds; a lower role, another user's record and a guest are refused (decision table: role × action).
- [ ] A direct URL, a changed id and a method override are refused server-side, not just hidden in the view.

**Eloquent and saved state**
- [ ] Only the intended columns change; related records, timestamps and soft deletes behave as the RC says.
- [ ] Delete, restore and re-edit after the change (state transitions).

**Migrations**
- [ ] The migration applies on an existing database with data and rolls back cleanly on a disposable copy.

**Queues, mail and events**
- [ ] With `QUEUE_CONNECTION=database` or `redis`, run `php artisan queue:work --once` and check the result is persisted;
      browser success alone does not prove the job ran.
- [ ] With `MAIL_MAILER=log`, read the message in `storage/logs/laravel.log` (subject, recipient, link) instead of sending real mail.

**Blade and frontend**
- [ ] Output is escaped for markup in user data; flash messages and errors appear.
- [ ] Changed pages at the viewports the RC names, at least one narrow (375 px) when layout changed.
- [ ] Keyboard access and visible focus for changed controls; axe on the changed component.

**Cache**
- [ ] After changing the underlying data the page shows the new value without a manual cache clear.

## Familiar Laravel problems (error guessing)

- Mass assignment: a request field sets a column the form never offered.
- A route works for the owner but also for any logged-in user (missing Policy or scoped binding).
- Validation only in the browser; the same request sent directly is accepted.
- N+1 queries make a list page slow with more than a handful of rows.
- A job works once but runs twice on retry, or never runs because no worker is started.
- `env()` returns null after `config:cache`.
- A migration that passes on SQLite fails on MySQL (or the reverse); enum, JSON and default values differ.
- A leftover `dd()` or `dump()` breaks the response.
- Stale cached data after an edit; old Vite build served after a frontend change.

Verify persistence by reopening the record through the application or a read-only `tinker` query of the
necessary record only. Track created users, rows and files with IDs and reasons; list data left behind and any
cleanup that still needs a decision. Respect the agreed scope for sending mail, running integrations and queues.
