## Plugin

<plugin folder, for example `plugins/ready-check`>

## Change

<What changes and why. No client code, names, URLs or data.>

## How to verify (QA)

<Setup, steps and expected results for the affected flow, or a link to the QA plan.>

## Checklist

- [ ] The plugin's own checks pass (for Ready Check: `python3 -B scripts/validate-package.py` and the tests)
- [ ] `python3 -B scripts/validate-catalog.py` passes when a catalog changed

Ready Check improvements prepared by its `contribute` skill use `plugins/ready-check/templates/improvement.md`.
