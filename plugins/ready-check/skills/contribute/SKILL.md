---
name: contribute
description: Prepare a pull request to the Ready Check plugin repository from an approved general improvement (a checklist item, QA technique, rule or bug fix), using the repository's improvement template, with no client data; publish only after the user agrees. Use when reflect's decision includes "PR to Ready Check" or the user asks to contribute an improvement to Ready Check.
---

# Contribute an improvement to Ready Check

Respond in the user's language; write the change and the PR text in English. Never include client code, names,
URLs, data or screenshots: describe the problem in general terms and write any example from scratch.

## 1. Prepare the change

- The plugin root is two directories above this file's directory. Read its `CONTRIBUTING.md` and
  `templates/improvement.md`. The source repository is the Keledones catalog; the plugin lives in its
  `plugins/ready-check` folder.
- Read the `repository` field of `<plugin>/.claude-plugin/plugin.json`.
  - **Set:** clone it into `<data root>/contrib/ready-check` (or `git fetch` an existing clone there), create a branch
    `improve/<short-slug>` from the default branch and work in `plugins/ready-check`. Never edit the installed plugin package.
  - **Not set:** patch-only mode. Copy the installed package (without `.git`) to a temporary directory twice, edit one
    copy, and produce the patch with `git diff --no-index <original> <changed>` with paths relative to the package
    root.
- Apply the smallest change that carries the proposal, in the right file (for example a checklist item in
  `profiles/drupal/review.md`, section I). One change per PR.
- Run `python3 -B scripts/validate-package.py` in the working copy; fix anything it reports.

## 2. Write the PR text

Fill `templates/improvement.md`: title `[<profile>] <review|qa|rule|bug>: <short>`, Problem, Evidence (counts from
reflect and a minimal example written from scratch), Proposed change (file, section, exact item), Why it is general,
How it was checked, Checklist. For a Ready Check bug the user does not want to fix, fill `templates/bug.md`
instead.

## 3. Show and decide

Show the diff and the PR text. Ask whether to publish.

- **Yes, repository set:** read the message format with `scripts/ready-check.py template commit --project <repo>`
  from the installed plugin. Commit with a message in that format covering the change, reason and verification.
  Push the branch (to the user's fork when they lack write access) and open the PR with `gh pr create` (GitHub)
  or `glab mr create` (GitLab) using the filled contribution template. If the CLI is missing or not authenticated,
  say so and fall back to saving files.
- **No, or patch-only mode:** save `improvement.patch` and `pr.md` to `<data root>/contrib/out/<slug>/` and give their
  paths so the user can send them to the author.

Never publish without the user's explicit yes, and never push to the plugin's main branch.
