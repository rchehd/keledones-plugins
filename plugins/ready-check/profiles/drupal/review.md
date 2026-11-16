# Drupal review checklist

Apply the general `review` workflow with this checklist. Review only what the change touches:

1. Classify every changed path (and new, deleted or renamed file) into change types using the map below.
   One file can have several types; read the diff, not only the filename.
2. Run section A always. Run every other section whose trigger matches at least one change type.
3. Check each item of a triggered section against the current code and record it as `CHECKED`, `FINDING`,
   `INCOMPLETE` or `N/A` with a one-line reason. An item is `N/A` only when the change cannot affect it.
4. List the untriggered sections once, each with the reason (for example "I. Render and cache: no render
   output, templates or access results changed").
5. The practices/security part of the review passes when every triggered item is `CHECKED`, `N/A` with a reason,
   or a nonblocking note. A `FINDING` blocks only when it is a demonstrated defect: wrong API for the installed
   version, a security hole, a regression, or a broken upgrade path. Style preferences stay advisory.

The user's and team's extra items (`customize list --kind review`) join the matching sections below.
These items are review prompts for the affected code, not new feature requirements. Consult the official API
documentation and change records for the installed versions when an item depends on the version.

## Change-type map

| Change type | Typical paths and signals | Sections |
| --- | --- | --- |
| PHP code | `src/**/*.php`, `*.module`, `*.inc`, `*.theme`, hooks | A, B |
| Routes and controllers | `*.routing.yml`, `src/Controller/`, route subscribers | B, C, H |
| Forms | `src/Form/`, `hook_form_alter`, `#ajax` callbacks | B, D, H |
| Entities, fields and queries | `src/Entity/`, field definitions, `hook_entity_*`, entity query, database API | B, E |
| Services and plugins | `*.services.yml`, `src/Plugin/`, event subscribers | B |
| Module configuration | `config/install/`, `config/optional/`, `config/schema/` | F |
| Site configuration | exported config directory (for example `config/sync/`), config split | F |
| Install and update code | `*.install`, `hook_update_N`, `*.post_update.php`, `hook_deploy_*` | G |
| Permissions and access | `*.permissions.yml`, access checks, `hook_*_access` | H |
| Render output and templates | render arrays, `*.html.twig`, preprocess, blocks, access results | I |
| Frontend | `*.js`, `*.css`/`*.scss`, `*.libraries.yml`, `drupalSettings` | J |
| User-visible strings | `t()`, `$this->t()`, `TranslatableMarkup`, `Drupal.t()`, Twig `t`/`trans` | K |
| Files and external calls | file/upload APIs, stream wrappers, `http_client`, process execution | L |
| Dependencies | `composer.json`, `composer.lock`, patches, `*.info.yml` | A, M |

Any change that reads untrusted input or produces output also triggers the security items of its sections;
there is no separate generic security pass.

## A. Versions and APIs (always)

- [ ] Installed Drupal core and PHP versions recorded from `composer.lock` and runtime evidence, not from ranges.
- [ ] Contributed modules and libraries used by the changed code recorded with installed versions.
- [ ] Changed code uses no API deprecated or removed for that core version; uncertain cases checked in change records.
- [ ] `core_version_requirement` in changed `*.info.yml` files matches the installed core.

## B. PHP code, services and plugins

- [ ] Classes get services through dependency injection (`create()` / service arguments), not `\Drupal::` calls,
      except in procedural hooks and static contexts where injection is impossible.
- [ ] Service definitions point to existing classes and arguments; plugin annotations or attributes match the
      plugin type of the installed core.
- [ ] Errors are handled or logged through a logger channel; nothing swallows exceptions silently.
- [ ] Callers and implementations of changed signatures, services, hooks and events are updated, including
      unchanged files that static checks do not cover.

## C. Routes and controllers

- [ ] Every new or changed route has an access requirement fitting its audience (`_permission`, `_entity_access`,
      `_custom_access`, `_role`); `_access: 'TRUE'` only for intentionally public routes.
- [ ] Upcasted entity parameters are access-checked for the operation, not only loaded.
- [ ] State-changing routes reachable by GET use `_csrf_token` or move to a form or POST.
- [ ] Responses that depend on user, route or content carry cacheability metadata (see I).

## D. Forms

- [ ] Every input constrained by an RC is validated server-side in `validateForm()`, not only in the browser.
- [ ] `#access` and hidden elements are not the only protection for a privileged action.
- [ ] Submit handlers save through config or entity APIs and change only the intended values.
- [ ] AJAX callbacks return the expected structure and keep form state across rebuilds.

## E. Entities, fields and queries

- [ ] Content entity queries call `accessCheck()` explicitly with the intended value.
- [ ] Database queries use placeholders or the query builder; no user input is concatenated into SQL.
- [ ] Entity changes alter only the intended fields and statuses; saves happen once per operation.
- [ ] Field or entity definition changes have an update path for existing sites (see G).

## F. Configuration

- [ ] Every new or changed config object in a module has matching schema in `config/schema/` with correct types.
- [ ] Module config declares its module and config dependencies; no site-specific `uuid` or `_core` values.
- [ ] Code reading config uses keys that exist in the schema and defaults.
- [ ] Changed defaults reach existing sites: the project's mechanism (update hook, post-update or config import
      of the exported directory) is identified; `config/install` alone does not update installed sites.
- [ ] Exported site config is consistent with its dependencies and any config split for the environments.

## G. Install, update and deploy code

- [ ] New `hook_update_N` numbers follow the existing ones; post-update names are unique; updates are idempotent
      and batch large data sets.
- [ ] Updates do not duplicate what the deployment's config import already does.
- [ ] `hook_install` / `hook_uninstall` create and remove the state, config and data they own.

## H. Permissions and access

- [ ] New permissions are declared with a title (and `restrict access` when sensitive) and used by the routes or
      checks that need them.
- [ ] The path of a lower-privilege or anonymous user is traced for changed routes, forms and entity operations.
- [ ] Ownership checks exist where the RC limits an action to the owner.
- [ ] Access results carry cacheability (`AccessResult::cachePerPermissions()`, `addCacheableDependency()`).

## I. Render output, templates and cache

- [ ] Render arrays that vary by user, role, route, language or query carry the matching cache contexts.
- [ ] Output derived from entities or config carries their cache tags; changes to them invalidate it.
- [ ] `max-age` is set only when content truly expires; caching is not disabled as a workaround.
- [ ] Twig does not apply `|raw` to user data; `Markup::create()` is used only for trusted markup.
- [ ] Preprocess functions that add data also add its cacheability.

## J. Frontend: JavaScript, styles and libraries

- [ ] Assets are attached through a library in `*.libraries.yml` with its dependencies (`core/drupal`, `core/once`).
- [ ] Behaviors use `Drupal.behaviors` with `once()`, so AJAX reattachment does not duplicate handlers.
- [ ] Selectors are scoped to the behavior context and work with several instances on one page.
- [ ] Data reaches JavaScript through `drupalSettings` or data attributes, not inline scripts.
- [ ] Styles are scoped to the component and cover the viewports the RC names.

## K. Translations

- [ ] New user-visible strings go through the translation API in PHP, Twig and JavaScript.
- [ ] Placeholders use the right prefix (`@`, `%`, `:` for URLs); variables and user content are not passed to `t()`.

## L. Files and external calls

- [ ] Uploads validate extension and size, use the intended public or private scheme and record file usage.
- [ ] External requests use the `http_client` service with timeouts and handled errors; secrets stay out of logs.
- [ ] No shell command is built from user input.

## M. Dependencies

- [ ] New or updated packages are compatible with the installed core and PHP; patches are documented.
- [ ] `composer audit` output, when available, is reviewed as advisory evidence.

## Hand-off to QA

- [ ] Each RC states whether it targets existing sites, fresh installations or both.
- [ ] Items the code cannot settle (active config, permissions, enabled modules, roles, languages, warm and cold
      cache, AJAX reattachment) become concrete planned QA checks, not guesses.
- [ ] No updates, config imports or cache rebuilds were run during review.

References: [Updating configuration](https://www.drupal.org/docs/drupal-apis/update-api/updating-configuration),
[Render-array cacheability](https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays),
[Writing secure Drupal code](https://www.drupal.org/docs/administering-a-drupal-site/security-in-drupal/writing-secure-code-for-drupal).
