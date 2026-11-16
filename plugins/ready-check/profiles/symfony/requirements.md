# Symfony task preparation

Read `profile.json` in this directory for detection signals and the profile version. Schema version `1`
describes task preparation and the doctor/static entry points. Read `static.md` before running those checks.

## Detection

Treat the application as a Symfony candidate when `composer.json` requires one of `detection.composer_packages`
or a file in `detection.files` (`bin/console`, `symfony.lock`) exists in the application root. Drupal and Laravel
applications are detected first (profile `priority`), so a Symfony component dependency alone never selects this
profile. A missing vendor directory does not prevent detection from declared dependencies. `composer.json`, PHP
files, DDEV, or Docker alone are insufficient. A bundle or library without an application has nothing to run here:
ask which Symfony app hosts its QA and do not invent one. If other framework evidence contradicts the detection,
ask which application is in scope.

## Setup prerequisites

Managed profile setup needs an installed Symfony 7.4 or newer (read the version from `composer.lock`, not from a
Composer range), PHP 8.2+, Composer and Node.js 20+ in the selected runner. Symfony CLI with a local PHP, DDEV
(type `symfony`) and a Docker Compose service that runs PHP (symfony-docker `php`, or any service with Composer
and Node.js) all work. Do not run `composer install` or `bin/console` commands merely to manufacture a setup
prerequisite.

## Requirement questions

Ask only when the task leaves a relevant behavior unclear:

- Which users, roles, Voters or `access_control` rules may perform the changed action, and what do others see?
- Which entity fields may the user set through the form, and which must stay server-controlled?
- Which validation constraints and messages apply to the input?
- What must persist after reload, and what happens to existing rows (migration, defaults, backfill)?
- Is the work synchronous, or should it go through Messenger (async transport, retries, failure transport)?

Record possible migration, Messenger, cache and environment concerns as planned review or setup questions. They
are not confirmed defects. Keep task acceptance criteria separate from suggested Symfony regression checks.
