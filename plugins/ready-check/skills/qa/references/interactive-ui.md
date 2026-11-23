# Ready Check interactive views

Use the view when the user chooses the interactive path. Offer the chat path whenever the view is unavailable
or the user prefers it. Save the report first. View actions are dated by the report round and tied to the
prepared content revision. They do not publish comments, run QA, change a verdict, or edit code by themselves.

## Prepare and open

Write a UTF-8 JSON input beside the existing report in its task directory. Run the portable entry point:

```text
<python> <plugin>/scripts/ready-check.py ui prepare --project <repo> --task <task-id> --view <view> --input <report-relative.json>
```

Call the packaged `ready-ui` server's `show_view` with the repository path, task ID and view. It renders the
same bundle as an MCP App when supported and otherwise returns a local URL. If the MCP tool is unavailable,
run the local server in a background command and use its printed URL:

```text
<python> <plugin>/scripts/ready-check.py ui serve --project <repo> --task <task-id> --view <view>
```

Give the URL to the user and ask them to return to the chat when finished. An MCP App may send a short
notification after saving. When notified or the user returns, read the saved decision once:

```text
<python> <plugin>/scripts/ready-check.py ui decision --project <repo> --task <task-id> --view <view>
```

`PENDING` means no decision has been saved. A timeout, opening the page, or a chat notification is not approval. The plan
and review views store one submission per prepared state. Compare task, round, and applicable revision with
the current report before acting. Apply a plan or review decision only while it is pending. Prepare again
whenever the underlying plan, findings or results change.

## QA plan

Use `qa-plan`. Include each scenario in the approved-plan format, even when some are optional. Use
`recording` for an approved-plan proposal and `recording_required` for a scenario that needs video to pass.
The user's selected recordings are returned separately from selected scenarios.
Before opening or replacing the view, update the report's `QA plan revision: <number>` and
`Requirements revision: <number>` lines. Both values must match the input and remain current when
the decision is submitted or read. Restore missing keys in older reports using their recorded revisions.
Include `environment`, `preconditions`, `execution`, `test_data`, `cleanup`, and `recording_scope` when
applicable. Each accepts a short string or a list of strings. State the actual environment, data actions and
recording retention in the plan before asking for approval.

```json
{
  "locale": "en",
  "title": "Account settings",
  "round": 1,
  "qa_plan_revision": 1,
  "requirements_revision": 1,
  "scenarios": [{
    "id": "QA-001",
    "title": "Change display name",
    "required": true,
    "required_reason": "Covers RC-001",
    "requirements": ["RC-001"],
    "risk": "High",
    "role": "Member",
    "environment": "Local test site",
    "preconditions": "The temporary member fixture is available.",
    "test_data": "Create a temporary display name.",
    "cleanup": "Restore the fixture's original display name.",
    "steps": ["Edit the name and save.", "Reload the page."],
    "expected": "The updated name persists.",
    "evidence": "Screenshot after reload"
  }]
}
```

Map `approve` to the existing approval fields, including only the returned recording IDs.
`revise` supplies scenario notes or edits to the exploratory charter. Update the plan, increment its
revision and seek approval again. `cancel` stops QA for the current run and records the user decision.

## QA results

Use `qa-results` with `round`, optional `status` and `coverage`, and `scenarios` containing current results.
Use the plan's titles, roles and RCs, actual versus expected and, for a confirmed failure, the minimal
observed steps. Add `artifacts` only for evidence intended to be shown. Each item has `path` relative to the
report directory under `evidence/`, optional `title`, and, for video, optional
`chapters: [{"title": "Save", "start": 2.5}]` with seconds from the retained clip. Serve screenshots and
video files from the report. Use distinct paths per round and attempt to preserve earlier evidence.
Add text excerpts only after redacting client sessions, secrets and credentials.
Use either medium or both according to the approved evidence plan and observed outcome.

Map `retest` to a new QA round according to the existing recheck rules. `draft` prepares a draft using the
`draft` skill and leaves publication to its own authorization. Record a `false-positive` decision and reason,
then investigate the affected result before changing its classification.
The command returns the current `decision` and `previous_decisions` for earlier view revisions. Check both
even when the current decision is null. Each decision names its original round and revision. Its `actions`
contain `id`, `action`, `scenario` and `reason`. Check the report's Decisions for the revision and action ID
before processing, and record the outcome to avoid repeats. Use the original round's evidence for drafts
and false-positive investigations. Before running a retest from an earlier revision, check that the
scenario is still in the current approved plan. If its scope changed or a later run already covers it,
record the outcome and seek fresh approval if more QA is needed.

## Review and static findings

Before inspecting code or running the static analysis that supplies the findings, capture the source:

```text
<python> <plugin>/scripts/ready-check.py ui snapshot --project <repo> --view review
```

Keep the returned `reviewed_source` and the reviewed requirements revision with the corresponding findings
in the report. Use `review` with `round`, `findings`, that same `reviewed_source` and
`requirements_revision`. The report's `Requirements revision: <positive integer>` line must match.
Add the line to older reports if the recorded revision is known. If findings came from different
snapshots or requirements revisions, refresh them before combining them. If the original snapshot is unavailable, use the
chat path or inspect the code again. Include `id`, `title`, `description`, `severity`, `source`,
`file`, `line`, `requirements`, and a concise optional `snippet` for each finding. Use only the current scope.
Record the returned row decisions and reasons in the report. Send `fix` IDs to the normal `check` fix
workflow in the current conversation. Immediately before any edit, read `ui decision` again to confirm
that the saved decision still matches the reviewed branch, working-tree fingerprint, and requirements revision.
Refresh the findings and ask for a new decision if any of those changed. A user's recorded risk acceptance or false-positive choice requires
re-evaluating the evidence and applicable requirements before any change to the gate.

## Settings

Use `settings` with the repository path and no task or input. The widget reads and saves the same project
preferences as `config`; it includes browser mode, check reminders, task capture, and PhpStorm MCP.
Pass `ide_status` (or `--ide-status` for the local server) as `available` after a successful inspection
or `unavailable` when the requested connection cannot be inspected. Leave it unverified otherwise.
After a PhpStorm connect action or its MCP App notification, read
`ui decision --project <repo> --view settings`. Continue the [PhpStorm setup flow](../../setup/references/phpstorm.md)
only for a pending `connect-phpstorm` decision. If the notification includes an ID, require it to match
the pending `request_id`. Pass that ID to `setup --component phpstorm --phpstorm-request <request_id>`
to apply the widget request. Stop if the decision is missing or the command reports cancellation or
replacement. Report the IDE connection as verified after an inspection succeeds.
