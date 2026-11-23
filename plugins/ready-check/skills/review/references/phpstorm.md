# Optional PhpStorm code inspections

Read `ready-check.py config get phpstormMcp --project <repo>`. When the preference is off, continue the
ordinary review. When enabled, use the currently advertised PhpStorm MCP inspection tools when the IDE has
the correct project open. Pass its verified `projectPath` and use file paths relative to that IDE project.
Inspect only files in the established review scope. Resolve source paths to the repository paths used in
the report, including linked Drupal extensions.

Prefer `lint_files` when advertised, with warning severity and a bounded batch. Otherwise use
`get_file_problems` with `errorsOnly: false`. Use the advertised schema. Avoid repeated calls after an
unavailable project, tool error, timeout, or disconnected IDE. Record the optional source as unavailable
with its reason and carry on with the same review gates.

Treat messages as candidate evidence. Read the saved code at the cited line and compare the task diff.
An unsaved editor result, different source revision, or a record outside the scope does not support a
finding. Deduplicate matching causes at the same location against static and review findings, and cite
PhpStorm as a source with the file, line and IDE severity. Suggest fixes for verified warnings worth
addressing. A blocker needs the same demonstrated trigger and impact as any other review finding, and
fixes go through the existing user decision in `check`. Use only inspection tools for this workflow.
