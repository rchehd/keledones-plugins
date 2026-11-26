# Ready Check QA results and evidence

## QA results

Record the current `Round: <number>` in the task report. Post the result using the packaged
[Markdown QA template](../../../templates/qa-results.md). Replace its placeholders with verified results
and artifact links. Keep the section order and IDs. Translate displayed status labels. Repeat the scenario block by ID, with
failed cases first.
Count every case once by recorded status. For a failed case, include its finding ID, impact, brief steps
to reproduce and decisive evidence. For a case that did not run, say why in the actual result field.
Report gaps in RC coverage, deviations from the plan, unresolved defects and remaining risks. Mark
empty sections explicitly. Localize titles, labels and evidence captions to the chat language.

Use the [client's supported preview format](evidence.md#create-a-replay-and-hand-off-from-qa) for selected
screenshots. Put a regular file or replay link beside each selected recording. Add an inline player when
the active client supports it. Keep the task report link in the message even when a preview opens. Use the
same observed results to prepare the local HTML report when the round has screenshots or recordings.

### Local HTML report

Write a UTF-8 JSON input beside the existing report. Set `locale` to the chosen report language tag.
The viewer supplies labels for English, Ukrainian and Russian. For another language, copy the
`en` object from [the QA labels](../../../ui/qa-labels.json) into the input's `labels` property.
Translate every value, preserving keys and nested objects. Write every displayed title, expected and actual result, artifact caption, video
chapter, coverage note and limitation in the selected language. Keep scenario IDs, status codes and
file paths as recorded.
Copy each scenario's `kind` and [`category`](test-design.md#coverage-categories) from its approved plan by ID.
The viewer translates these labels and shows them beside the title, for example `[Browser; User flow]`.
If a recorded plan lacks either field, omit that field.
The report uses its effective artifact language. When reopening an existing round, refresh the viewer input
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
The HTML report shows screenshot pairs together and lets the user enlarge either image. Each clip has
its own player and chapter controls. For a retest, select the original failed evidence explicitly in the
current round and pair it with the fresh evidence. Keep the original files in their attempt directories.

Prepare the HTML report and start the loopback server in a background command:

```text
<python> <plugin>/scripts/ready-check.py ui prepare --project <repo> --task <task-id> --view qa-results --input <report-relative.json>
<python> <plugin>/scripts/ready-check.py ui serve --project <repo> --task <task-id> --view qa-results
```

Add the printed URL as a regular Markdown link. The URL is local and time limited. Include the task report
path so the evidence remains findable after expiry. For a user on another machine or a remote client,
explain where the report is stored. When asked to open the report and the client's visible browser can
reach it, open the printed URL there. This opens saved evidence without rerunning QA. Prepare the latest
round before creating a new link and report any preparation or server error in chat.

When verifying changes to the HTML report, check the failed-first order, status colors, screenshot
enlargement, and playback and seeking for an approved video.

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
