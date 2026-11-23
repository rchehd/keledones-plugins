# QA action journal and video

Add the evidence choice to the existing QA plan approval. Identify the browser or mobile scenarios to record,
the capture method, and what to keep. Ask for recording approval before execution. For approved cases, start
capture on the first attempt so a failure can be shown as it happened. Keep failure footage by default. Keep
successful footage when the approved plan calls for it as evidence, for a requested demo, or as a required result.
Journal the executed steps for every scenario.

Start capture after authentication and stop before switching accounts or showing unrelated content. Use test
data and verify the file exists, plays and depicts the planned test surface before linking it. Stop a recording
on failure or cancellation too. If capture is unavailable or unsafe, record the reason and use the journal and
other observed evidence. Optional video alone does not change the case verdict.

## Record actions as they happen

After a meaningful action and its observation, run the following with the prepared task ID from `reports` and
the current round. Use the client language in chat and the report language in the journal.

```sh
python3 <plugin>/scripts/ready-check.py qa-record --project <app> --task <task-id> --round 1 \
  --case QA-001 --attempt 1 --actor agent --action "Submit the draft" \
  --expected "The list includes the saved draft" --observed "The draft appears in the list"
```

Use `py -3` on native Windows. Each invocation appends a timestamped entry to
`evidence/round-1/QA-001-steps.md` and returns its paths and a `step_id` for attaching a video timestamp.
Number attempts from 1 within each case and round. Use the same `--attempt` for every step of that attempt
and increment it for a retry. The journal labels each step with its attempt.
The journal uses fenced text blocks for the action, expected result and observed output. Keep meaningful
whitespace when passing sanitized commands and output so users can copy them from the rendered journal.
Choose `user` for an action the user performed and `runner` for an observed test-runner step. For API,
CLI and CI cases record the actual request or command and result in redacted form. For a project runner
record the invocation, observed case results and emitted artifacts. List internal test steps only when the
runner provides that trace. Copying the intended plan is not evidence that its steps happened.

Use the journal with the actual observed oracle and relevant screenshots, exit status, response excerpts
or state checks. Summarize actions in your own words. Leave credentials, tokens, private URLs, request
headers, raw tool transcripts and sensitive test data out of the journal.

## Prepare a private recording destination

Before starting a recording, choose a fresh filename of the form `QA-001-attempt-1.webm`, using the same
case and attempt number as the journal. Use a new number for a retry within the same round.
`qa-record --prepare-video` creates an empty private attempt directory and verifies that Git ignores the
whole directory, including any extra clips the recorder creates. Use the returned `path` or report-relative
`evidence` with the recorder and `video` with `qa-replay`. For MP4 recordings use the `.mp4` extension.

```sh
python3 <plugin>/scripts/ready-check.py qa-record --project <app> --task <task-id> --round 1 \
  --case QA-001 --attempt 1 --prepare-video QA-001-attempt-1.webm
```

## Annotate approved web recordings

Use the existing managed Chromium bundle. Record the actual approved actions. Before each meaningful action
group, add a short title and an expected outcome. Keep the pointer, action label and target outline visible
during clicks. After verifying the final state, give the viewer time to read it and include the observed
result in a short closing caption. Presentation timing belongs to the recording. Apply the scenario's
normal assertions and waits when judging behavior. For a latency-sensitive scenario, keep action pacing
out of the measured run. Playwright can record every tab in its session, including tabs opened during
capture. Use a session that contains only tabs and test data approved for this case.

- **Ready Check Playwright CLI.** Open the named session from the task report directory. Start after login
  and use the same session for recording and UI actions. Use the `evidence` path returned by the preparation
  command. The managed wrapper accepts these arguments even if the application has no Playwright tests.

  ```sh
  playwright-cli -s=<session> video-start evidence/round-1/QA-001-attempt-1.webm.capture/QA-001-attempt-1.webm
  playwright-cli -s=<session> video-show-actions --duration=950 \
    --point-style="width:16px;height:16px;border:2px solid white;border-radius:50%;background:#187580" \
    --highlight-style="outline:3px solid #187580;border-radius:6px"
  playwright-cli -s=<session> video-chapter "Save the draft" --description="The draft should appear in the list" --duration=1800
  ```

  Perform the actual actions and check the result. Add later chapters as needed and call
  `playwright-cli -s=<session> video-stop` before closing the session. Verify the output path.
- **Ready Check Playwright MCP.** Call `browser_start_video` in the approved visible session, enable
  `browser_video_show_actions` with pointer, point and highlight styles as above, and use
  `browser_video_chapter` with short titles and descriptions. Stop with `browser_stop_video`.
  Use the prepared destination when the server supports it. Otherwise verify that the server writes all clips
  to a private directory outside the worktree or ignored by Git before recording. Copy the verified clips
  into the prepared directory with the chosen filename and numbered suffixes for extra clips. Reload the
  client after updating the plugin if these tools are absent.
- **Project Playwright Test, Cypress or other runner.** Reuse the video and trace emitted by the approved
  invocation. Verify that automatic capture excludes authentication and account changes. Check recording
  and upload settings and isolate the output of each invocation using the [project runner guidance](project-tests.md).

## Capture approved mobile scenarios

- **Maestro.** `maestro record --local` starts capture before the first flow step. Use it only for a flow
  that preserves the planned assertions and begins with authentication already complete, if applicable.
  Confirm that the flow has no login, reauthentication, account switch, or reset that exposes credentials.
  Use the approved device and verify that the installed version can write to the prepared clip path or another
  private location. If authentication is part of the flow, keep the approved test invocation and use a device
  recorder only after authentication, when the procedure allows it. Otherwise use the journal and report the
  capture limitation.
- **Android and iOS Simulator.** Use the same approved device as the native QA case. Android can record via
  `adb -s <serial> shell screenrecord <unique-device-file>.mp4`. Stop that recording gracefully and use
  `adb -s <serial> pull <unique-device-file>.mp4 <case-evidence-file>.mp4`. On macOS use
  `xcrun simctl io <UDID> recordVideo <case-evidence-file>.mp4` and stop it gracefully. This also works for
  a manually exercised app, without Maestro. Remove only the temporary device file created for this capture.

## Desktop, CLI, API and CI

Use the journal and the evidence appropriate to the case. Include screenshots from the available desktop
UI tool, redacted command output and exit status, HTTP checks, or links to the specific CI job or step.
Attach a desktop recording supplied by the user when it covers the same case and contains approved data.
For user-guided cases, identify which actions and results the agent observed and which the user reported.

## Create a replay and hand off from QA

Decide what to keep and what to show separately for each attempt once its outcome is known. Preserve the
journal, expected and observed result, and relevant evidence in the report. In chat, show the evidence
that establishes the result for the case.

| What the case checks | Evidence to show beside the scenario ID |
| --- | --- |
| Stable layout, visible message or saved form state | Show a screenshot of the decisive state. Use two labeled screenshots when the comparison matters, such as before and after or two orientations. |
| Timing, focus movement, animation, drag or intermittent behavior | Show the approved and verified video when playback is supported. For a long recording, link the replay and give the relevant steps or timestamps. |
| A sequence and a final visual state | Show both if each establishes something different. Label the moment shown in the clip and the state visible in the screenshot. |
| API, persistence, accessibility scan or CI result | Show the decisive observed value or short diagnostic excerpt. Link the trace, journal or raw result. Use a screenshot or clip when a separate visual claim needs it. |

Use a Markdown image for a verified, client-accessible screenshot with a label that describes the shown state.
For a short video use the client's inline media preview when supported. Put “Replay with steps” beside it
in the user's language when available. If inline playback is unavailable, give a direct video link when the
file is accessible in that client. For long recordings, give a replay link and the relevant timestamps.
Keep other evidence in the report. Never present a planned action, placeholder or inaccessible file as
observed evidence. If no video was approved or the clip is unavailable, state the limitation when it affects
what can be shown and link the evidence actually collected.

Report failures as soon as observed. A retry is unnecessary to produce a picture or clip of an already
observed failure. On a passing retry, report both outcomes and keep the failed attempt's evidence available.
Show a planned demo or required video even on `PASS`. Use the actual passing attempt's clip when video is
required. Discard temporary passing footage if the approved plan retained failures only.

Delete only temporary files created by Ready Check for the current passing attempt. Preserve other artifacts,
user-supplied recordings, and any runner video that also contains a failed or unknown attempt. When a runner
mixes outcomes in one video, cite the failed test or timestamp. Report why expected footage is unavailable
and include the journal and other observed evidence.

Store every retained clip in the prepared attempt directory. Copy verified runner clips there before starting
another invocation, cleaning its output, or sharing a link. Build replays and link videos from this evidence
directory so later runs cannot invalidate earlier links.

For required video, record the observed outcome when capture finishes, after journaling the attempt and
storing the clip. Use the resulting `evidence` and `attempt`
in the [QA gate input](gate.md). A failed attempt's video can still be shared after a passing retry, but
required proof for the retry must come from the retry itself.

```sh
python3 <plugin>/scripts/ready-check.py qa-record --project <app> --task <task-id> --round 1 \
  --case QA-001 --attempt 1 --finish-video QA-001-attempt-1.webm.capture/QA-001-attempt-1.webm --outcome PASS
```

After the recording is finished, pass verified times as repeatable `--at <step_id>=<seconds>` arguments
to `qa-replay` for a retained clip. Use offsets from this clip's start, including chapter timing. The player
shows only steps from that attempt. Each time is tied to the finished file's SHA-256. Steps from the same
attempt without a timestamp for that file stay visible as text. For extra clips from
the same attempt, use each clip's actual relative path, for example
`QA-001-attempt-1.webm.capture/QA-001-attempt-1-1.webm`. Link the additional clips separately.

```sh
python3 <plugin>/scripts/ready-check.py qa-replay --project <app> --task <task-id> --round 1 \
  --case QA-001 --video QA-001-attempt-1.webm.capture/QA-001-attempt-1.webm --at <step-id>=7.25
```

Use the user's language. Put the evidence under the matching scenario ID and verdict, followed by links
to the journal or replay. Use the path format supported by the current client:

- **Codex Desktop:** Write `![Observed card layout]` immediately followed by `(/absolute/path/QA-001.png)`.
  Use the same syntax with a WebM or MP4 path when the client supports inline playback.
- **Cursor Agents Window:** Use a workspace-relative path in the Markdown image for a screenshot in the
  workspace. Link the video file or replay for playback outside the chat.
- **Claude Code Desktop:** In a local session, link the video or HTML replay so it opens in the Browser
  pane. Link the screenshot file when the client cannot preview it inline.

For terminal and remote sessions, use a preview or link the active client can access. Keep report
references relative to the task and media local.

[Playwright CLI video](https://github.com/microsoft/playwright-cli/blob/v0.1.23/skills/playwright-cli/references/video-recording.md) ·
[Playwright MCP](https://github.com/microsoft/playwright-mcp/blob/v0.0.84/README.md) ·
[Maestro local recording](https://docs.maestro.dev/maestro-flows/workspace-management/record-your-flow) ·
[Android recording](https://developer.android.com/tools/adb#screenrecord) ·
[iOS Simulator recording](https://developer.apple.com/videos/play/wwdc2020/10647/?time=880)
