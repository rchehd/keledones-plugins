# Contributing to Ready Check

Ready Check improves from real use. Most improvements are small: a checklist item, a QA technique, a profile fix or
a bug fix. The `contribute` skill prepares such a pull request from an approved `reflect` proposal.

## What fits

- General review or QA checklist items for a profile (`profiles/<id>/review.md`, `profiles/<id>/qa.md`).
- Fixes to skills, hooks and scripts, with a minimal reproduction.
- New framework profiles under `profiles/<id>/`.

Project-specific rules belong in the project's own `.ai/ready-check/` customizations, not here.

## Privacy

Never include client code, names, URLs, data or screenshots. Describe the problem in general terms and write a
minimal example from scratch.

## How to check a change

```sh
python3 -B scripts/validate-package.py
claude plugin validate --strict .
```

Then try the change on one task with your client and describe the result without client details.

## Pull requests

- One change per pull request.
- Use the improvement template; title `[<profile>] <review|qa|rule|bug>: <short description>`.
- Checklist items are short, checkable and in English, matching the existing style.

Bugs you do not want to fix yourself: open an issue with the bug template.
