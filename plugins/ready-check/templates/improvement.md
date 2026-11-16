<!-- Title: [<profile>] <review|qa|rule|bug>: <short description> -->

## Problem

<What Ready Check missed or got wrong, described in general terms. No client code, names, URLs or data.>

## Evidence

- Seen in <N> of <M> tasks; returned after human review <K> times; missed by Ready Check <L> times.
- Minimal example (written from scratch, not copied from a project):

```text
<smallest snippet or steps that show the problem>
```

## Proposed change

- File: `<profiles/<id>/review.md | profiles/<id>/qa.md | skills/... | scripts/...>`
- Section: `<checklist section>`
- Change: `<exact new or changed checklist item, rule or code change>`

## Why it is general

<Why this applies beyond one project or team.>

## How it was checked

- [ ] `python3 -B scripts/validate-package.py` passes
- [ ] Tried on a task (describe briefly, without client details)

## Checklist

- [ ] No client code, names, URLs or data
- [ ] One change per pull request
- [ ] Wording matches the checklist style (short, checkable, English)
