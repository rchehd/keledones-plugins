# Symfony review checklist

Apply the general `review` workflow with this checklist. Review only what the change touches:

1. Classify every changed path (and new, deleted or renamed file) into change types using the map below.
   One file can have several types; read the diff, not only the filename.
2. Run section A always. Run every other section whose trigger matches at least one change type.
3. Check each item of a triggered section against the current code and record it as `CHECKED`, `FINDING`,
   `INCOMPLETE` or `N/A` with a one-line reason. An item is `N/A` only when the change cannot affect it.
4. List the untriggered sections once, each with the reason (for example "I. Messenger: no message, handler
   or transport changed").
5. The practices/security part of the review passes when every triggered item is `CHECKED`, `N/A` with a reason,
   or a nonblocking note. A `FINDING` blocks only when it is a demonstrated defect: wrong API for the installed
   version, a security hole, a regression, or a broken migration path. Style preferences stay advisory.

The user's and team's extra items (`customize list --kind review`) join the matching sections below.
These items are review prompts for the affected code, not new feature requirements. Consult the official
Symfony documentation for the installed version when an item depends on the version.

## Change-type map

| Change type | Typical paths and signals | Sections |
| --- | --- | --- |
| PHP code | `src/**/*.php`, `config/*.php` | A, B |
| Controllers and routes | `src/Controller/`, `#[Route]`, `config/routes*`, `redirectToRoute`, `$request->` | B, C, E |
| Services and configuration | `config/services.yaml`, `config/packages/`, `#[Autowire]`, `#[AsAlias]`, tags, `.env` | B, J |
| Security | `config/packages/security.yaml`, `src/Security/`, Voters, `#[IsGranted]`, `access_control`, firewalls | D |
| Forms and CSRF | `src/Form/`, `createForm`, `isCsrfTokenValid`, `csrf_token()`, `form_start` | E, F |
| Doctrine entities and queries | `src/Entity/`, `src/Repository/`, `EntityManager`, DQL, `QueryBuilder`, `createQuery` | B, G |
| Migrations | `migrations/`, `doctrine:migrations` | G |
| Twig and rendered output | `templates/**/*.twig`, `\|raw`, `{% autoescape %}`, `path()`, `form()` | H |
| Serializer and API | `#[Groups]`, `#[Ignore]`, `JsonResponse`, `MapRequestPayload`, API Platform resources | F, K |
| Messenger | `src/Message/`, `src/MessageHandler/`, `config/packages/messenger.yaml`, `#[AsMessageHandler]` | I |
| Cache | `cache.app`, `CacheInterface`, tags, HTTP cache headers, `#[Cache]` | L |
| Translations | `translations/*.xlf`, `*.yaml`, `trans()`, `\|trans` | M |
| Frontend assets | `assets/`, `importmap.php`, `webpack.config.js`, `package.json` | N |
| Dependencies | `composer.json`, `composer.lock`, `symfony.lock`, `package-lock.json` | A, O |

Any change that reads untrusted input or produces output also triggers the security items of its sections;
there is no separate generic security pass.

## A. Versions and APIs (always)

- [ ] Installed Symfony and PHP versions recorded from `composer.lock` and runtime evidence, not from ranges.
- [ ] Changed code uses no API deprecated or removed in the installed version (`bin/console debug:container
      --deprecations` or the upgrade notes when unsure).
- [ ] Packages and bundles used by the changed code recorded with installed versions.

## B. PHP code, services and autowiring

- [ ] Dependencies arrive through constructor or action-argument autowiring, not `$container->get()` or static state.
- [ ] Services stay small and stateless; configuration values come from parameters or `#[Autowire]`, not `getenv()`.
- [ ] Controllers stay thin: validation in forms or constraints, access in Voters, work in services.
- [ ] Exceptions are handled or logged; nothing swallows them silently; no debug calls (`dump`, `dd`, `var_dump`) remain.
- [ ] Callers and implementations of changed signatures, interfaces and events are updated, including unchanged
      files that static checks do not cover.

## C. Controllers and routes

- [ ] Every new or changed route restricts HTTP methods (`methods: ['POST']`) to what it needs.
- [ ] No GET (or other safe-method) route changes state; deletes and updates use POST, PUT, PATCH or DELETE.
- [ ] `#[MapEntity]`/param converters resolve only records the user may access (scoped by owner where needed).
- [ ] Responses and redirects match the RC for success, validation failure and not-found cases.
- [ ] Login, password and token routes are rate limited (`rate_limiter`, `login_throttling`).

## D. Security voters and access_control

- [ ] Every protected action is guarded by `#[IsGranted]`, `denyAccessUnlessGranted()` or an `access_control` rule.
- [ ] Voters decide ownership and roles; they do not trust request data, and `supports()` is narrow.
- [ ] The path of a lower-privilege or anonymous user is traced for changed routes, entities and actions.
- [ ] `access_control` order is correct (first match wins) and new paths are not left public by a broader rule.
- [ ] Passwords use `PasswordHasherInterface`; secrets and tokens are not logged or rendered.

## E. Forms and CSRF

- [ ] Forms keep CSRF protection on (`csrf_protection` not disabled); the token field is rendered.
- [ ] Non-form state changes (links, AJAX) validate a token with `isCsrfTokenValid()` or `#[IsCsrfTokenValid]`.
- [ ] Only intended fields are mapped (`data_class`, no `mapped` hole to protected properties); no `$request->request->all()` writes.
- [ ] Constraints (`#[Assert\...]`) cover type, length, range and uniqueness (`UniqueEntity`) server-side.
- [ ] Validation errors and submitted values reach the template.

## F. Serializer and API payloads

- [ ] Serialization groups or DTOs expose only the intended fields; secrets and internal ids stay out.
- [ ] Incoming payloads use `#[MapRequestPayload]` or a form with validation, not the raw request body.
- [ ] Error responses and status codes match the contract (400/403/404/422).

## G. Doctrine entities, migrations and queries

- [ ] Mapping changes come with a migration; `doctrine:schema:validate --skip-sync` stays clean.
- [ ] A new migration has a working `down()` (or a stated reason), does not edit a deployed migration, and states
      its effect on large tables (locks, defaults, nullable columns for existing rows).
- [ ] DQL and `QueryBuilder` use bound parameters (`setParameter`); no user input is concatenated into queries.
- [ ] Relations used in loops or templates are fetched with joins; no query per item (N+1).
- [ ] Large sets use pagination or `toIterable()`, not `findAll()` into memory.
- [ ] Multi-step writes that must succeed together share one `flush()` or a transaction.

## H. Twig and escaping

- [ ] User data is output with `{{ }}`; `|raw`, `{% autoescape false %}` and `markup` are used only for trusted,
      sanitized HTML.
- [ ] Forms render CSRF tokens and errors; links use `path()`/`url()`, not hard-coded URLs.
- [ ] JavaScript receives data through `data-*` attributes or `|json_encode`, not string concatenation.
- [ ] Strings that must be translated go through `|trans` when the app is multilingual.

## I. Messenger

- [ ] Handlers are idempotent and safe to retry; retry strategy and the failure transport are intentional.
- [ ] Messages carry ids or small value objects, not entities or secrets.
- [ ] Routing sends slow work to an async transport, and a worker consumes it in the target environment.
- [ ] Dispatch happens after the transaction commits when the handler reads the new data.

## J. Configuration and environment

- [ ] New parameters and env vars have defaults or an entry in `.env`, and no secrets are committed (use secrets or `.env.local`).
- [ ] `when@prod`/`when@dev` blocks keep debug tooling out of production.
- [ ] Autowiring and `autoconfigure` defaults still match the services directory layout; `lint:container` passes.
- [ ] Changed defaults reach existing environments through the project's deploy process (cache warmup, migrations).

## K. API contract

- [ ] Changed endpoints keep backward-compatible fields, or the break is stated in the RC.

## L. Cache

- [ ] Cache keys include every variable the value depends on (user, locale, tenant, filters).
- [ ] Cached data is invalidated when its source changes (tags, `delete()`), not only by TTL.
- [ ] Per-user data is never cached under a shared key or in a public HTTP cache.

## M. Translations

- [ ] New keys exist for every supported locale (or the fallback is intentional); `lint:xliff` passes.
- [ ] Placeholders and plurals match between source and translation.

## N. Frontend assets

- [ ] Assets load through AssetMapper or the project's bundler, and built output is not committed unless the project does so.
- [ ] Changed JavaScript is scoped, handles `fetch` errors, and works with several instances on one page.
- [ ] Styles cover the viewports the RC names; interactive elements keep keyboard access and visible focus.

## O. Dependencies

- [ ] New or updated packages are compatible with the installed Symfony and PHP; Flex recipes reviewed; licenses and maintenance checked.
- [ ] `composer audit` output, when available, is reviewed as advisory evidence.

## Hand-off to QA

- [ ] Each RC states whether it applies to existing data, fresh installs or both.
- [ ] Items the code cannot settle (roles in effect, transports, cache pools, migrations applied, fixtures loaded)
      become concrete planned QA checks, not guesses.
- [ ] No migrations, fixtures, cache clears or Messenger workers were run during review.

References: [Symfony security](https://symfony.com/doc/current/security.html), [forms](https://symfony.com/doc/current/forms.html),
[CSRF](https://symfony.com/doc/current/security/csrf.html), [Doctrine](https://symfony.com/doc/current/doctrine.html),
[Messenger](https://symfony.com/doc/current/messenger.html).
