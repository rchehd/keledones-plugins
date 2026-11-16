---
name: customize
description: Add, list, disable or remove the user's Ready Check coding rules and extra review or QA checklist items, for this project or globally. Use when the user asks to add a review rule, remember a check for the project, add a QA scenario to the checklist, show their rules, or disable a rule; also used by reflect to apply approved proposals.
---

# Customize Ready Check

Respond in the user's language. All writes go through one script; never edit the plugin package.
Resolve the plugin root two directories above this file's directory. Python: `python3`, or `py -3` on Windows.

## What can be customized

| Kind | Where it acts | Example |
| --- | --- | --- |
| `rule` | Every session's context and every review (MUST rules block) | "Prefer switch over long if/elseif chains" |
| `review` | One section of the profile's review checklist | Section "I. Render output, templates and cache": "Output varying by role has the user.roles context" |
| `qa` | The profile's QA checklist or its familiar problems | Section "Forms": "Submit with an expired session" |

Scopes: `project` (`<repo>/ai/ready-check/…`, git-excluded) or `global` (the user's data folder, all projects).

## Steps

1. Map the request to kind, text, profile (from `ai/ready-check/settings.json`, usually `drupal`), section (the
   profile checklist heading the item belongs to; `Familiar problems` for QA error guesses) and `--must` for rules
   that must block.
2. If the user did not say project or global, ask once.
3. Run one command:
   - add: `ready-check.py customize add "<text>" --kind <kind> --scope <scope> --project <app> [--profile drupal --section "<section>"] [--must]`
   - list: `ready-check.py customize list --project <app> [--kind <kind>]`
   - disable / enable: `ready-check.py customize disable "<text>" --scope <scope> --project <app>` (a project scope
     disable also hides a global item or a client-settings rule in this project)
   - remove: `ready-check.py customize remove "<text>" --kind <kind> --scope <scope> --project <app> [--profile drupal]`
4. Show what changed and the file. For project items, say how to share them with the team:
   `git add -f ai/ready-check/rules.md ai/ready-check/extensions` (then commit as usual).

An item that already exists is not added twice. A remove that matches several items asks for a more specific text.
