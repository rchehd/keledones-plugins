# Ready Check QA evidence viewer

## QA results

Record the current `Round: <number>` in the report first. Open the viewer when that round has screenshots or recordings
worth showing. Describe scenario outcomes in chat and include the report path. Use the viewer for evidence
and the chat for decisions about the result.

Write a UTF-8 JSON input beside the existing report. Set `locale` to match the current chat language:
`uk` for Ukrainian, `ru` for Russian and `en` for English or other chat languages. The viewer translates
its built-in labels. Write every displayed title, expected and actual result, artifact caption, video
chapter, coverage note and limitation in the selected language. Keep scenario IDs, status codes and
file paths as recorded.
Copy each scenario's `kind` and [`category`](test-design.md#coverage-categories) from its approved plan by ID.
The viewer translates these labels and shows them beside the title, for example `[Browser; User flow]`.
If a recorded plan lacks either field, omit that field.
The report keeps its configured file language. When reopening an existing round, refresh the viewer input
if its displayed text uses mixed languages or a different language from the current viewer locale.

This example uses English:

```json
{
  "locale": "en",
  "round": 1,
  "scenarios": [{
    "id": "QA-001",
    "title": "Save the display name",
    "kind": "browser",
    "category": "user-flow",
    "status": "PASS",
    "expected": "The saved name remains after reloading.",
    "actual": "The name remained after reloading.",
    "artifacts": [
      {"path": "evidence/round-1-saved.png", "title": "Saved state"},
      {"path": "evidence/round-1-save.webm", "title": "Save and reload",
       "chapters": [{"title": "Reload", "start": 2.5}]}
    ]
  }]
}
```

List only approved evidence files under `evidence/`. Select screenshots, clips or both according to the
[evidence plan](evidence.md). Keep distinct paths per round and attempt. The optional chapter positions
are measured in seconds from the start of the retained clip. Redact sensitive data before showing evidence.
Link trace files, replay HTML and logs from the local task report.

For a before/after comparison, list both screenshots, both clips, or both pairs under the same scenario.
Label each item `Before` or `After` in the user's language, adding the original round or attempt if it differs.
Available screenshot previews appear as clickable thumbnails in the widget, up to two per scenario. A pair
appears together with its captions. Each thumbnail opens a larger view. **Compare screenshots** remains
available on demand when neither preview was included. A missing preview can load on demand when the host
supports it. Otherwise the widget offers the local HTML, which shows the full pair when both files are available.
For a retest, select the original failed evidence explicitly in the current round's view and pair it with the
fresh evidence. Keep the original files in their original attempt directories. Each clip has its own playback
controls and chapters.

Prepare and open the view:

```text
<python> <plugin>/scripts/ready-check.py ui prepare --project <repo> --task <task-id> --view qa-results --input <report-relative.json>
```

Call the packaged `ready-ui` server's `show_view` with the repository path, task ID and `view: qa-results`.
A compatible host shows the result card, screenshot enlargement and a play button for on-demand playback of
supported clips up to 4 MB. The opening response includes the local report URL when the server can bind a local port.
Small screenshots are also sent in bounded app metadata, so compatible cards can show previews when the
host cannot proxy tool calls. The card uses its local link for **Open local report** and for media it cannot
load inline. On click, it requests a visible tab in the client's browser when the host supports sending
requests from the widget. It can also ask the host to open the URL and keeps it available beside the action.

When the card or a user action asks to open the local QA report, use the current client's browser tool to
open the printed URL in a visible tab that can reach Ready Check's loopback server. This navigation opens
the saved report without rerunning QA. If the client cannot reach the local URL, give it for opening in the
browser on the machine where Ready Check is running. If `show_view` is unavailable or could not start the
local server, start the HTML view in a background command and use the printed URL:

```text
<python> <plugin>/scripts/ready-check.py ui serve --project <repo> --task <task-id> --view qa-results
```

The URL is local and time limited. Include the task report path so the user can find the evidence after it
expires. Keep the status and decisive evidence reference in the chat summary even when the viewer opens.
When the task report moves to the next round, prepare the current evidence before opening a fresh viewer.

Handle retest, false-positive investigation and comment drafts in chat. Retest starts a new QA round under
the existing recheck rules. Investigate the original round before reclassifying a result. Prepare a comment
through the draft skill and use its separate publication authorization.

## Review and static findings

Capture the source before inspecting code or running the static analysis that supplies the findings:

```text
<python> <plugin>/scripts/ready-check.py ui snapshot --project <repo> --view review
```

Record the returned `reviewed_source` and the reviewed requirements revision with the findings in the
report. Collect decisions in chat by finding ID. Before a fix, recapture the source and compare the branch
and fingerprint with the reviewed snapshot. Compare the current requirements revision too. If either
changed, refresh the findings and ask for a new decision.

## Saved decisions from earlier versions

Earlier plan, review and gallery decisions stay in their reports. Use `ui decision --project <repo> --task
<task-id> --view <qa-plan|review|qa-results>` to read decisions when resuming an older run. For QA results,
check `previous_decisions` too. Match the original round, revision and action ID with the report's Decisions
before applying a pending choice. Recheck the current scope and required approvals before any new action.
