# Symfony QA guidance

Apply this guidance to affected RCs and code paths. Use the Symfony version, runner and deployment process found
in the project; do not introduce new requirements merely because this is Symfony.

## Establish the local app

- Resolve the app URL and the runner (Docker Compose, Symfony CLI `symfony serve`, DDEV or `php -S`) from the
  project files and `bin/console about`. Check that the running app serves the working copy, including
  uncommitted files and built assets (`public/assets`, `public/build`). A title or Git HEAD alone does not establish this.
- Read `.env`, `.env.local` values only for the facts QA needs (`APP_ENV`, `DATABASE_URL` driver,
  `MAILER_DSN`, `MESSENGER_TRANSPORT_DSN`). Never copy secrets, `APP_SECRET` or tokens into the report.

## Resolve required preparation

Determine whether the changed path needs a migration, fixtures, `assets:install`, an asset build, a cache clear or a
running Messenger worker. Inspect the project's own process. Report missing preparation and obtain the decision
instead of silently running `doctrine:migrations:migrate`, `doctrine:fixtures:load`, `doctrine:schema:update`
or `cache:clear`. Record the commands executed and their results when preparation is authorized, then recheck
the source identity and rerun affected stages.

## Test user and login

Use a test user, not an administrator, for non-admin behavior. When the approved plan covers test data, take the
user from the project's Doctrine fixtures (`doctrine:fixtures:load --append` only with approval) or create one
through the runner with the project's own command or `bin/console dbal:run-sql`/a short PHP script using the
password hasher. When the `login_link` authenticator is configured, generate a link
(`LoginLinkHandlerInterface`) instead of typing a password. Keep the generated credentials only in
`.ai/ready-check/qa-accounts.json` (local, never committed, never in the report or PR draft), log in through the
app's form, and list the user as test data. Never reuse real accounts or production credentials; never create
users on a shared or production database.

## QA checklist by change type

The user's and team's extra items (`customize list --kind qa`) join the matching sections and the familiar problems.
Use the change types from the [review checklist](review.md#change-type-map). Plan scenarios from the sections the
change triggers; list the others once with the reason. Each item names the technique it relies on.

**Forms and validation**
- [ ] Main submit with valid data, then reload: saved values are shown (persistence).
- [ ] Required, empty, too long and invalid values show readable errors and keep old input (equivalence classes).
- [ ] Extra request fields (`role`, `id`, `createdAt`) do not change protected properties (error guessing).
- [ ] Double submit, back after submit, refresh; an expired session or CSRF token gives a clean error (state transitions).

**Routes, access and voters**
- [ ] Intended role succeeds; a lower role, another user's record and an anonymous visitor are refused (decision table: role x action).
- [ ] A direct URL, a changed id and a changed HTTP method are refused server-side, not just hidden in the template.
- [ ] State-changing URLs opened with GET (link, address bar) do not change data.

**Doctrine and saved state**
- [ ] Only the intended columns change; related records and timestamps behave as the RC says.
- [ ] Delete and re-edit after the change; deleting an already deleted record gives a clean 404 (state transitions).

**Migrations**
- [ ] The migration applies on an existing database with data and rolls back cleanly on a disposable copy.

**Messenger, mail and events**
- [ ] With an async transport, run `bin/console messenger:consume --limit=1` and check the result is persisted; browser success alone does not prove the handler ran.
- [ ] With `MAILER_DSN=null://null` or a local catcher, read the message (subject, recipient, link) instead of sending real mail.

**Twig and frontend**
- [ ] Output is escaped for markup in user data (try `<b>x</b>` and a quote); flash messages and form errors appear.
- [ ] Changed pages at the viewports the RC names, at least one narrow (375 px) when layout changed.
- [ ] Keyboard access and visible focus for changed controls; axe on the changed component.

**Cache**
- [ ] After changing the underlying data the page shows the new value without a manual cache clear.

## Familiar Symfony problems (error guessing)

- A delete or update link works over GET with no CSRF token, so a crafted image tag or link triggers it.
- A route works for the owner but also for any logged-in user (missing Voter or `#[IsGranted]`).
- `|raw` or `autoescape false` renders stored user input as HTML (stored XSS).
- Validation only in the browser (`required`, HTML5); the same request sent directly is accepted.
- N+1 queries make a list page slow with more than a handful of rows; the profiler shows the query count.
- A handler works once but runs twice on retry, or never runs because no worker is started.
- Works in `dev` but fails in `prod`: stale cache, missing `assets:install`, `when@dev` only config, env vars.
- A migration that passes on SQLite fails on PostgreSQL/MySQL (or the reverse); types and defaults differ.
- A leftover `dump()`/`dd()` breaks the response or leaks data in the page.
- Missing or untranslated keys show raw message ids for a non-default locale.

Verify persistence by reopening the record through the application or a read-only query of the necessary
record only. Track created users, rows and files with IDs and reasons; list data left behind and any cleanup
that still needs a decision. Respect the agreed scope for sending mail, running integrations and workers.
