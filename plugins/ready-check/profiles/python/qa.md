# Python QA guidance

Apply this guidance to affected RCs and code paths. Use the framework, runner and deployment process found in the
project; do not introduce new requirements merely because this is Python.

## Establish the local app

- Resolve the app URL and runner (`manage.py runserver`, `uvicorn`, `flask run`, Docker Compose) from the project
  files. Check that the running app serves the working copy; a title or Git HEAD alone does not establish this.
- Read settings only for the facts QA needs (`DEBUG`, database engine, `ALLOWED_HOSTS`). Never copy secrets into the report.

## Resolve required preparation

Determine whether the changed path needs a migration, fixtures, `collectstatic` or a worker. Inspect the project's own
process. Report missing preparation and obtain the decision instead of silently running `migrate`, `loaddata`
or `flush`. Record the commands executed when preparation is authorized, then recheck the source identity.

## Test user and login

Use a test user, not a superuser, for non-admin behavior. When the approved plan covers test data, create one through the
runner: Django `createsuperuser --noinput` with `DJANGO_SUPERUSER_PASSWORD` from the environment (admin checks only) or
a short `manage.py shell` script that creates a plain user; FastAPI and Flask use the project's own user model or seed
command. Keep the credentials only in `ai/ready-check/qa-accounts.json` (local, never committed, never in the report),
log in through the app's form, and list the user as test data. Never use real accounts or production databases.

## QA checklist by change type

Use the change types from the [review checklist](review.md#change-type-map).

**Views and forms**
- [ ] Main submit with valid data, then reload: saved values are shown (persistence).
- [ ] Empty, too long and invalid values show readable errors and keep old input (equivalence classes).
- [ ] Extra request fields (`is_staff`, `id`, `owner`) do not change protected attributes (error guessing).
- [ ] Double submit, back after submit, expired session or CSRF token give a clean error (state transitions).

**Access**
- [ ] Intended role succeeds; a lower role, another user's record and an anonymous visitor are refused (decision table).
- [ ] A direct URL, a changed id and a changed HTTP method are refused server-side.

**Search and queries**
- [ ] Quotes, `%`, `_` and SQL fragments in the search box return results or an empty list, never an error (error guessing).

**Migrations**
- [ ] The migration applies on a copy of the database with data and rolls back cleanly.

**Templates**
- [ ] `<b>x</b>` and quotes in user data render as text; flash messages and form errors appear.
- [ ] Changed pages at the viewports the RC names; keyboard access and visible focus.

## Familiar Python problems (error guessing)

- SQL built with f-strings or `%` formatting; `'` in the search box breaks the page or leaks rows.
- `DEBUG = True` in a deployed settings file shows stack traces and settings to visitors.
- A debug `print()` or `breakpoint()` left in a view blocks or floods the server log.
- A model change without a migration works on a developer database but crashes on a fresh install.
- A view works for the owner but also for any logged-in user (missing permission or scoped lookup).
- `|safe` on stored user input renders it as HTML (stored XSS).
- N+1 queries make a list page slow with more than a handful of rows.
- Works with SQLite but fails on PostgreSQL (types, case-sensitive `LIKE`, constraints).

Verify persistence by reopening the record through the application or a read-only query. Track created users and
rows with IDs and reasons; list data left behind and any cleanup that still needs a decision.
