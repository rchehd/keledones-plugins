# Drupal task preparation

Read `profile.json` in this directory for detection signals and the profile version. Schema version `1`
describes task preparation and the doctor/static entry points. Read `static.md` before running those checks.

## Detection

Treat the application as a Drupal candidate when `composer.json` requires one of `detection.composer_packages`
or a file in `detection.core_paths` exists beneath the application root. A missing vendor directory does not
prevent detection from declared dependencies. `composer.json`, PHP files, DDEV, or Drupal-related tooling
alone are insufficient. Dependency names are exact matches; `drupal/core-composer-scaffold` alone is not proof.

A contributed module, installation profile, or theme may have no full site here. Ask whether it is meant to
be checked with the Drupal profile and which site will host QA. Do not invent the site or install Drupal.
If other framework evidence contradicts Drupal detection, ask which application is in scope.

## Setup prerequisites

Managed profile setup needs an installed Drupal 10/11 site, a compatible PHP 8.2+ runtime and Node.js 20+
in the selected runner. Identify the actual host site for a standalone module/theme. Read installed core
metadata and lock/runtime evidence rather than inferring the installed version from a Composer range.
Do not install Drupal or the site's dependencies merely to manufacture a setup prerequisite.

## Requirement questions

Ask only when the task leaves a relevant behavior unclear:

- Which roles and permissions should allow or deny the changed action?
- Which content type, entity, form, view, or route is affected?
- What must be saved, and what should remain visible after reload?
- Which languages or translated strings are part of the requested outcome?
- Does the change need to work on an existing site, a fresh install, or both?

Record possible configuration, update-hook, cache, and environment concerns as planned review or setup
questions. They are not confirmed defects and do not establish missing requirements by themselves.
Keep task acceptance criteria separate from suggested Drupal regression checks.
