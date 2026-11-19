---
name: draft
description: Draft a commit message, PR/MR title or description, or a first-person task update in chat at any point. Use for requests such as "write a commit message", "draft the pull request description", "prepare a merge request summary", "generate a task comment", or "summarize what I did for the ticket".
---

# Draft delivery text

Draft only what the user requested. A direct request for text authorizes drafting in the current chat. It
needs neither a completed Ready Check run nor a PR/MR. Keep check, commit, push, PR/MR creation and
external posting outside this skill.

1. Use the current task, known changes and actual results. Inspect the relevant Git diff with read-only
   commands and reuse any existing Ready Check report for this task. If a scope decision would materially
   change the text, ask which changes to include. For work still in progress, distinguish completed work
   from pending work and use verified results only.
2. Resolve Ready Check's root two directories above this file's directory. Run the template command for
   each requested artifact with `python3` (or `py -3` on Windows) and the current Git root:
   - Commit message: `scripts/ready-check.py template commit --project <repo>`
   - PR/MR title or body: `scripts/ready-check.py template pr --project <repo>`
   - Task comment: `scripts/ready-check.py template task-comment --project <repo>`
   Use the session hook's command if it includes a native client template option for task comments.
   Without a Git root, omit `--project` to resolve the user or default template. When template resolution
   fails, show its reason. With only the skill name and no artifact specified, ask which draft is wanted.
3. Return copyable text using the effective template. Write commit and PR/MR text in English. Write task
   comments in the current chat's language and in first person. The default comment uses numbered points
   for completed changes. Add a confirmed PR/MR link, checks or limitations when useful. Keep internal
   report paths, credentials and private evidence out of shareable text. If the user asks for PR/MR text
   during a partial or blocked check, include the current verdict and relevant outstanding checks.
