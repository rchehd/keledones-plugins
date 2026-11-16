---
name: uninstall
description: Remove what Ready Check created in the current project, and optionally its reports, task records and installed tools, after showing a preview.
---

# Ready Check uninstall

Respond in the user's language. Resolve the plugin root two directories above this file's directory and the
application from the conversation or workspace.

1. Preview first, always:
   `python3 <plugin>/scripts/ready-check.py uninstall --project <app> --dry-run`
   (`py -3` instead of `python3` on Windows PowerShell).
2. Show the user what will be removed and what is kept. By default the project's settings, last-check marker and
   temporary files go; `ai/ready-check/reports/` and `ai/ready-check/tasks/` stay, and so do the installed tools.
3. Ask once whether to also remove your rules and checklist extensions (`--custom`, kept by default), reports, task
   records and feedback (`--reports`) and the installed tools, user settings and hook state shared
   by all projects on this machine (`--data`; this includes the runner-side checkers, for example in the DDEV global cache).
4. Run the same command without `--dry-run`, with the chosen flags, and report the result.
5. Tell the user to remove the plugin itself with their client's plugin controls. Do not edit client settings.

Never delete anything the preview did not list.
