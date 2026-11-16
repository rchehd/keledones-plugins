# Laravel review checklist

Apply the general `review` workflow with this checklist. Review only what the change touches:

1. Classify every changed path (and new, deleted or renamed file) into change types using the map below.
   One file can have several types; read the diff, not only the filename.
2. Run section A always. Run every other section whose trigger matches at least one change type.
3. Check each item of a triggered section against the current code and record it as `CHECKED`, `FINDING`,
   `INCOMPLETE` or `N/A` with a one-line reason. An item is `N/A` only when the change cannot affect it.
4. List the untriggered sections once, each with the reason (for example "H. Queues and jobs: no job,
   listener or scheduled command changed").
5. The practices/security part of the review passes when every triggered item is `CHECKED`, `N/A` with a reason,
   or a nonblocking note. A `FINDING` blocks only when it is a demonstrated defect: wrong API for the installed
   version, a security hole, a regression, or a broken migration path. Style preferences stay advisory.

The user's and team's extra items (`customize list --kind review`) join the matching sections below.
These items are review prompts for the affected code, not new feature requirements. Consult the official
Laravel documentation for the installed version when an item depends on the version.

## Change-type map

| Change type | Typical paths and signals | Sections |
| --- | --- | --- |
| PHP code | `app/**/*.php`, `routes/*.php`, `config/*.php` | A, B |
| Routes and controllers | `routes/*.php`, `app/Http/Controllers/`, route model binding, middleware | B, C, G |
| Form Requests and validation | `app/Http/Requests/`, `$request->validate()`, `Validator::make` | B, D |
| Eloquent models | `app/Models/`, `$fillable`, `$guarded`, casts, scopes, relations, observers | B, E |
| Queries and data access | Eloquent/query builder, `DB::`, `whereRaw`, `with()`, collections over large sets | B, E, F |
| Migrations and seeders | `database/migrations/`, `database/seeders/`, factories | F |
| Authorization | `app/Policies/`, `Gate::`, `authorize()`, `can`, middleware, guards | G |
| Blade and rendered output | `resources/views/**/*.blade.php`, components, `{!! !!}`, `@csrf`, `@method` | I |
| Queues, jobs, events and mail | `app/Jobs/`, `app/Listeners/`, `app/Mail/`, `app/Notifications/`, schedule | H |
| Configuration and environment | `config/*.php`, `.env.example`, `env()` calls, service providers | J |
| Cache | `Cache::`, `remember`, tags, route/config/view caches | K |
| Frontend assets | `resources/js`, `resources/css`, `vite.config.js`, `package.json` | L |
| Dependencies | `composer.json`, `composer.lock`, `package-lock.json` | A, M |

Any change that reads untrusted input or produces output also triggers the security items of its sections;
there is no separate generic security pass.

## A. Versions and APIs (always)

- [ ] Installed Laravel and PHP versions recorded from `composer.lock` and runtime evidence, not from ranges.
- [ ] Changed code uses no API deprecated or removed in the installed version; uncertain cases checked in the
      upgrade guide and release notes.
- [ ] Packages used by the changed code recorded with installed versions.

## B. PHP code, services and structure

- [ ] Dependencies arrive through the container (constructor or method injection), not hidden static state.
- [ ] Controllers stay thin: validation in Form Requests, authorization in Policies, work in actions or services.
- [ ] Exceptions are handled or reported; nothing swallows them silently; no debug calls (`dd`, `dump`, `ray`) remain.
- [ ] Callers and implementations of changed signatures, contracts and events are updated, including unchanged
      files that static checks do not cover.

## C. Routes and controllers

- [ ] Every new or changed route has the right middleware (`auth`, `can:`, `throttle`, `verified`) for its audience.
- [ ] State-changing actions use POST, PUT, PATCH or DELETE with CSRF protection; no GET route changes state.
- [ ] Route model binding resolves only records the user may access (scoped bindings for nested resources).
- [ ] Responses and redirects match the RC for success, validation failure and not-found cases.
- [ ] Login, password, token and other sensitive routes have rate limiting.

## D. Form Requests and validation

- [ ] Every input constrained by an RC is validated server-side in a Form Request or `validate()`, not only in the browser.
- [ ] The controller uses `validated()` / `safe()` data, never `$request->all()` or unvalidated input for writes.
- [ ] Rules cover type, length, existence and uniqueness (`unique` ignores the current record on update).
- [ ] `authorize()` of a Form Request is not left returning `true` for a protected action.
- [ ] Validation error messages and old input reach the view.

## E. Eloquent models and mass assignment

- [ ] `$fillable` lists only fields users may set; `$guarded = []` or `unguard()` is not used on user-facing models.
- [ ] Sensitive fields (`role`, `is_admin`, `user_id`, status, price) cannot be set through request data.
- [ ] Casts, hidden attributes and appended attributes keep secrets out of arrays and JSON.
- [ ] Relations, scopes and observers do not hide extra queries or side effects the RC does not expect.
- [ ] Multi-step writes that must succeed together run in a transaction.

## F. Queries, N+1 and migrations

- [ ] Relations used in loops or views are eager loaded (`with()`); no query per item.
- [ ] Large sets use `chunk`, `cursor` or pagination, not `all()` or `get()` into memory.
- [ ] Raw SQL uses bindings; no user input is concatenated into `whereRaw`, `orderByRaw` or `DB::select`.
- [ ] A new migration has a working `down()`, does not edit an already deployed migration, and states its effect on large tables
      (locks, backfill, default values, nullable columns for existing rows).
- [ ] Indexes and foreign keys exist for new lookup columns and relations.
- [ ] Seeders and factories do not run in production paths and carry no real data.

## G. Authorization

- [ ] A Policy or Gate decides every protected action; the controller calls `authorize()` or middleware `can:`.
- [ ] The path of a lower-privilege or anonymous user is traced for changed routes, models and actions.
- [ ] Ownership is checked where the RC limits an action to the owner (query scoped to the user, or Policy).
- [ ] New abilities are registered or auto-discovered and covered by the routes that need them.

## H. Queues, jobs, events and mail

- [ ] Jobs are idempotent and safe to retry; `tries`, `backoff` and `failed()` handling are intentional.
- [ ] Jobs serialize ids or small models, not large objects or secrets; dispatch happens after the transaction commits
      (`afterCommit`).
- [ ] Mail and notifications use the queue when slow and are not sent twice on retry.
- [ ] Scheduled commands prevent overlap and have a bounded run time.

## I. Blade and rendered output

- [ ] User data is output with `{{ }}`; `{!! !!}` is used only for trusted, sanitized markup.
- [ ] Forms include `@csrf` and the right `@method`; old input and errors are displayed.
- [ ] Links use named routes; no hard-coded absolute URLs; JavaScript receives data through attributes or `@json`.
- [ ] Strings that must be translated go through `__()` or `@lang` when the app is multilingual.

## J. Configuration and environment

- [ ] `env()` is called only inside `config/*.php`; application code reads `config()` (config caching ignores `env()` elsewhere).
- [ ] New settings have defaults, an entry in `.env.example` and no secrets in the repository.
- [ ] Service providers register bindings once and keep boot work light.
- [ ] Changed defaults reach existing environments through the project's deploy process (config cache, migration).

## K. Cache

- [ ] Cache keys include every variable the value depends on (user, locale, tenant, filters).
- [ ] Cached data is invalidated when its source changes (`Cache::forget`, tags, model events), not only by TTL.
- [ ] Per-user data is never cached under a shared key; `rememberForever` is justified.

## L. Frontend assets

- [ ] Assets load through Vite (`@vite`) and the built manifest is not committed unless the project does so.
- [ ] Changed JavaScript is scoped, handles errors from `fetch`, and works with several instances on one page.
- [ ] Styles cover the viewports the RC names; interactive elements keep keyboard access and visible focus.

## M. Dependencies

- [ ] New or updated packages are compatible with the installed Laravel and PHP; licenses and maintenance checked.
- [ ] `composer audit` output, when available, is reviewed as advisory evidence.

## Hand-off to QA

- [ ] Each RC states whether it applies to existing data, fresh installs or both.
- [ ] Items the code cannot settle (roles, policies in effect, queue and mail drivers, cache store, migrations
      applied, seeded data) become concrete planned QA checks, not guesses.
- [ ] No migrations, seeders, cache clears or queue runs were executed during review.

References: [Laravel validation](https://laravel.com/docs/validation), [authorization](https://laravel.com/docs/authorization),
[Eloquent mass assignment](https://laravel.com/docs/eloquent#mass-assignment), [queues](https://laravel.com/docs/queues).
