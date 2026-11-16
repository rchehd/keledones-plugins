# Drupal QA guidance

Apply this guidance to affected RCs and code paths. Use the Drupal version, runner, site conventions, and
deployment process found in the project; do not introduce new requirements merely because this is Drupal.

## Establish the local site

- Resolve the site's URL and actual Drupal document root from the project/runner information. In a multisite
  installation identify the selected site and URI; a reachable default site may use a different database/config.
  For a standalone module/theme, identify a local host site that contains the checked working copy and version.
- Check that the runner serves the selected application, including uncommitted files and relevant generated
  assets. Inspect existing mount/build configuration and available runtime version/status information. A site
  title or Git HEAD alone does not establish this correspondence. Record evidence or the exact unresolved point.
- Use available read-only project tooling to inspect installed modules/theme, update status, active config,
  and relevant queues when necessary. Use the same runner/site URI as the application. Drush is a possible
  source, not an unconditional QA dependency: inspect its version/help and project commands before invoking it.
  Do not dump whole databases, configuration containing secrets, or session/login tokens into the report.

## Resolve required preparation

Determine whether the changed path depends on a database update, configuration import, cache rebuild,
asset build, fixture, or enabled component. Inspect the project's established preparation process. Report
missing preparation and obtain the needed decision/authorization instead of silently changing the site.
Do not automatically pull code, run updates/imports, rebuild caches, or enable extensions as part of checking.

If preparation is already authorized, record commands actually executed, results, and environment effects.
Recheck source identity (static snapshot when statics are selected) and runtime correspondence afterwards; rerun affected stages before claiming
coverage. Preparation failure is an environment blocker, not automatically a defect in the patch.

Distinguish fresh-install behavior from updates to an existing site. Testing newly installed configuration
does not prove that existing sites receive the required change. If the task requires both, use appropriate
test fixtures/sites or record incomplete coverage. Do not reset the database or install a new site implicitly.

## QA checklist by change type

The user's and team's extra items (`customize list --kind qa`) join the matching sections and the familiar problems.

Use the change types from the [review checklist](review.md#change-type-map). Plan scenarios from the sections the
change triggers; list the others once with the reason. Each item names the technique it relies on.

**Forms**
- [ ] Main submit with valid data, then reload: saved values are shown (persistence).
- [ ] Required, empty and invalid values (equivalence classes) show readable errors and keep entered data.
- [ ] Length or number limits: boundary and one past it (boundary values).
- [ ] Double submit, back after submit, refresh (state transitions).
- [ ] AJAX parts still work after a rebuild or a validation error.

**Routes, access and permissions**
- [ ] Intended role succeeds; a lower role and anonymous get the expected denial (decision table: role × action).
- [ ] Another user's record and a direct URL to a restricted page are refused server-side.

**Entities and saved state**
- [ ] Only the intended fields and statuses change; revisions and workflow behave as the RC says.
- [ ] Delete, unpublish or re-edit after the change (state transitions).

**Render output and cache**
- [ ] Output is correct for anonymous and authenticated users, with a warm cache (do not clear caches before every
      observation; that hides stale output).
- [ ] After editing the underlying content or config, the page shows the new value without a manual cache clear.

**Configuration and updates**
- [ ] The active value and the feature using it behave as expected on the intended site.
- [ ] When the RC covers existing sites, the change arrives through the project's update or config-import path.

**Frontend**
- [ ] Changed pages at the viewports the RC names, at least one narrow (375 px) when layout changed.
- [ ] Behaviors work after AJAX and with several instances on one page; no duplicated handlers.
- [ ] Keyboard access and visible focus for changed controls; axe on the changed component.

**Translations**
- [ ] Changed strings in a configured second language, when the site has one.

**Async work**
- [ ] The queued or cron result is persisted and completes within a bounded time; browser success alone does not prove it.

## Familiar Drupal problems (error guessing)

- Cache not invalidated for anonymous users or another role after an edit.
- Access enforced only by hiding a link or button; the direct URL still works.
- JavaScript handlers attached twice after AJAX, or not attached at all after it.
- A library not attached on the page where the component appears.
- A config change that works on a fresh install but never reaches existing sites.
- Untranslated or double-escaped strings (`&amp;`, raw placeholders).
- A form that loses entered values after a validation error.

Use test accounts with the relevant configured roles. Do not use an administrator-only pass to establish
member or anonymous behavior. Log in without passwords: when the approved plan covers creating test data,
create a test user with the needed role through the runner (`drush user:create <name>`, then
`drush user:role:add <role> <name>`), and open the one-time link from `drush uli --name=<name> --no-browser`
in the agreed browser session. List created users in the report as test data. One-time login links are
authentication material and must not appear in the report, screenshots, or PR draft.

Verify persistence by reopening the entity through the application or another suitable read-only view.
If the acceptance condition specifically needs backend state, inspect only the necessary record/field or
log excerpt. Unavailable required state checks remain incomplete; avoid inventing database evidence.

Track created entities, users, files, and modifications with IDs and reasons. Avoid modifying existing
content when a test fixture is appropriate. Respect the agreed scope for sending email, running integrations,
queue processing, and cleanup. List data left behind and any cleanup that still requires a decision.
