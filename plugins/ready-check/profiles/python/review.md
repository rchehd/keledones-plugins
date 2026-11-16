# Python review checklist

Apply the general `review` workflow with this checklist. Review only what the change touches:

1. Classify every changed path (and new, deleted or renamed file) into change types using the map below.
2. Run section A always. Run every other section whose trigger matches at least one change type.
3. Check each item of a triggered section against the current code and record it as `CHECKED`, `FINDING`,
   `INCOMPLETE` or `N/A` with a one-line reason. List the untriggered sections once, each with the reason.
4. The review passes when every triggered item is `CHECKED`, `N/A` with a reason, or a nonblocking note. A `FINDING`
   blocks only when it is a demonstrated defect: a security hole, a regression, a wrong API for the installed version
   or a broken migration path. Style preferences stay advisory.

The user's and team's extra items (`customize list --kind review`) join the matching sections below.

## Change-type map

| Change type | Typical paths and signals | Sections |
| --- | --- | --- |
| Python code | `**/*.py` | A, B |
| Database access | `models.py`, `.raw(`, `cursor.execute`, `text(`, SQLAlchemy sessions | C |
| Views, routes, endpoints | `views.py`, `urls.py`, `@app.get`, `APIRouter`, `request.` | D, E |
| Serializers and schemas | DRF serializers, Pydantic models, forms | F |
| Migrations | `migrations/`, `alembic/` | G |
| Settings and secrets | `settings*.py`, `.env`, `DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY` | H |
| Templates | `templates/**/*.html`, `\|safe`, `mark_safe`, `autoescape` | I |
| Async and background work | `async def`, `await`, Celery, threads | J |
| Dependencies | `pyproject.toml`, `requirements*.txt`, lock files | A, K |

## A. Versions and APIs (always)

- [ ] Installed Python and framework versions recorded from lock files and runtime evidence, not from ranges.
- [ ] Changed code uses no API deprecated or removed in the installed versions (`python -W error` or the release notes when unsure).
- [ ] No `print()`, `breakpoint()` or `pdb` calls remain; logging goes through `logging`.

## B. Code quality

- [ ] Exceptions are specific; no bare `except:` or silent `except Exception: pass`.
- [ ] No mutable default arguments or module-level state shared between requests.
- [ ] Callers and implementations of changed signatures are updated, including unchanged files that static checks do not cover.
- [ ] Type hints on changed public functions match the real behavior.

## C. Database access

- [ ] Queries use the ORM or bound parameters; no user input is formatted into SQL (`f"..."`, `%`, `.format`, `+`).
- [ ] Relations used in loops or templates use `select_related`/`prefetch_related`; no query per item (N+1).
- [ ] Large sets use pagination or `iterator()`, not `all()` into memory.
- [ ] Multi-step writes that must succeed together run in one transaction (`atomic`).

## D. Views and authorization

- [ ] Every new or changed view checks authentication and permission (`login_required`, permission classes, dependencies).
- [ ] Objects are looked up scoped to the user; a changed id cannot reach another user's record.
- [ ] State changes use POST/PUT/PATCH/DELETE, never GET.
- [ ] CSRF protection stays on (`csrf_exempt` only with a stated reason); tokens are rendered in forms.

## E. Input handling

- [ ] Request data is validated by forms, serializers or Pydantic models before use; no raw `request.POST`/body writes to models.
- [ ] File uploads check type and size and never use client file names as paths.
- [ ] Redirects and URLs built from input are validated (`url_has_allowed_host_and_scheme`).

## F. Serializers, forms and schemas

- [ ] Only intended fields are exposed or writable (`fields`/`exclude`, `read_only_fields`, response models).
- [ ] Validation covers type, length, range and uniqueness server-side; errors reach the client.

## G. Migrations

- [ ] Model changes come with a migration; `makemigrations --check` stays clean.
- [ ] A migration is reversible (or states why not), does not edit an applied migration, and states its effect on large tables.

## H. Settings and secrets

- [ ] `DEBUG` is never hard-coded to `True`; `ALLOWED_HOSTS` is not `['*']` outside development.
- [ ] `SECRET_KEY`, passwords and tokens come from the environment, not the repository or logs.
- [ ] Secure cookies, HTTPS redirect and HSTS settings are intentional (`manage.py check --deploy`).

## I. Templates

- [ ] User data is escaped; `|safe`, `mark_safe` and `{% autoescape off %}` appear only on trusted, sanitized HTML.
- [ ] JavaScript receives data through `json_script` or `data-*` attributes.

## J. Async and background work

- [ ] No blocking calls (ORM, `requests`, file IO) inside `async def` without a thread or async client.
- [ ] Tasks are idempotent and safe to retry; they receive ids, not model instances or secrets.

## K. Dependencies

- [ ] New or updated packages are compatible with the installed Python and framework; licenses and maintenance checked.
- [ ] `pip-audit` output, when available, is reviewed as advisory evidence.

## Hand-off to QA

- [ ] Items the code cannot settle (permissions in effect, migrations applied, settings per environment) become
      concrete planned QA checks.
- [ ] No migrations, fixtures or management commands were run during review.

References: [Django security](https://docs.djangoproject.com/en/stable/topics/security/), [deployment checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/),
[Bandit](https://bandit.readthedocs.io/), [Ruff rules](https://docs.astral.sh/ruff/rules/).
