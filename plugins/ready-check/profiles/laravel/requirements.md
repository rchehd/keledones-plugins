# Laravel task preparation

Read `profile.json` in this directory for detection signals and the profile version. Schema version `1`
describes task preparation and the doctor/static entry points. Read `static.md` before running those checks.

## Detection

Treat the application as a Laravel candidate when `composer.json` requires one of `detection.composer_packages`
or a file in `detection.files` (`artisan`) exists in the application root. A missing vendor directory does not
prevent detection from declared dependencies. `composer.json`, PHP files, DDEV, or Sail alone are insufficient.
A package or library that only depends on `illuminate/*` has no application here: ask which Laravel app hosts
its QA and do not invent one. If other framework evidence contradicts the detection, ask which application is
in scope.

## Setup prerequisites

Managed profile setup needs an installed Laravel 12 or newer (read the version from `composer.lock`, not from
a Composer range), PHP 8.2+ and Node.js 20+ in the selected runner. Sail, DDEV (type `laravel`) and a local
PHP all work. Do not run `composer install` or `artisan` commands merely to manufacture a setup prerequisite.

## Requirement questions

Ask only when the task leaves a relevant behavior unclear:

- Which users, roles, Policies or Gates may perform the changed action, and what do others see?
- Which model fields may the user set, and which must stay server-controlled?
- Which validation rules and error messages apply to the input?
- What must persist after reload, and what happens to existing rows (migration, defaults, backfill)?
- Is the work synchronous, or should it be queued, retried or sent as mail or a notification?

Record possible migration, queue, cache and environment concerns as planned review or setup questions. They
are not confirmed defects. Keep task acceptance criteria separate from suggested Laravel regression checks.
