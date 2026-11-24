# Ready Check QA evidence viewer

## QA results

Record the current `Round: <number>` in the report first. Open the viewer when that round has screenshots or recordings
worth showing. Describe scenario outcomes in chat and include the report path. Use the viewer for evidence
and the chat for decisions about the result.

Write a UTF-8 JSON input beside the existing report:

```json
{
  "locale": "en",
  "round": 1,
  "scenarios": [{
    "id": "QA-001",
    "title": "Save the display name",
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
With two screenshots in a scenario, **Compare screenshots** shows both together in the widget. If only one
can load there, it stays visible beside a button for the local HTML, which shows the full pair when both files
are available. Each image can be enlarged independently.
For a retest, select the original failed evidence explicitly in the current round's view and pair it with the
fresh evidence. Keep the original files in their original attempt directories. Each clip has its own playback
controls and chapters.

Prepare and open the view:

```text
<python> <plugin>/scripts/ready-check.py ui prepare --project <repo> --task <task-id> --view qa-results --input <report-relative.json>
```

Call the packaged `ready-ui` server's `show_view` with the repository path, task ID and `view: qa-results`.
A compatible host shows the result card, screenshot enlargement and on-demand playback of supported clips
up to 4 MB. The opening response includes the local report URL when the server can bind a local port.
The card uses that link for **Open local report**, unsupported or larger media, and hosts that cannot proxy
tool calls from widgets. If the host declines to open the URL, the widget shows it for copying.

If the card is unavailable and `show_view` returned a URL, give it. If the tool is unavailable or could not
start the local server, start the same HTML view in a background command and give the printed URL:

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
