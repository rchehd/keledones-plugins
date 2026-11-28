# Check the QA results against the approved plan

For a planned QA round save a JSON input beside the report and run:

```sh
<python> <plugin>/scripts/ready-check.py qa-gate --input <report-folder>/qa-gate-input-round-1.json
```

Use the approved scenario list for `scenarios` and current recorded observations for `results`.
Include every current in-scope requirement. For each acceptance condition that still needs runtime evidence,
include its verification in a required case. Use an empty requirement list for a regression case without an RC.
When resuming an older plan, derive the kind from the approved steps and keep the original scenario IDs.
An absent result is treated as `NOT_RUN`. `N/A` and `INCOMPLETE` need a reason. `PASS` and `FAIL` need
`evidence`: one path or a list of paths relative to the report folder, each a non-empty file saved there.
A missing, empty or outside file is listed in `missing_evidence`.

Set `approval` to the approved plan file and the user's exact reply: the chat message, or the option label
chosen in the question tool. The plan must be the newest `qa-plan-round-<N>-rev-<R>.md` revision of its
round. The gate finds that reply in the task records made after the plan file was saved and lists evidence
older than the approval in `evidence_before_approval`, except for a carried-over result with
`recorded_round`. Without a matching reply, or with a newer revision of that round, `approval_check` is
`UNVERIFIED`. With `captureTasks` off or no records for the branch it is `SKIPPED` and does not change the
verdict. Never edit a plan file after showing it; a changed plan is a new revision file.
`missing_evidence`, `evidence_before_approval` and an `UNVERIFIED` approval change `PASS` to `INCOMPLETE`;
an observed `FAIL` stays `FAIL`.
When the approved plan makes video mandatory, include the current `round` and set `recording_required: true`
on the required scenario. Use [`qa-record --finish-video`](evidence.md#create-a-replay-and-hand-off-from-qa)
with the actual outcome of the recorded attempt. Set `attempt` and `recording` on its result from the
command's `attempt` and `evidence` output. The gate matches the round, scenario, attempt, outcome and clip
digest against the recording entry. For a valid carried-over `PASS`, also set `recorded_round` to the original
round and provide `carry_over_reason` after checking that the recorded result is still current.
An absent, empty or mismatched clip is listed in
`missing_required_recordings` and changes `PASS` or `N/A` to `INCOMPLETE`. An observed `FAIL` stays `FAIL`.
Optional video does not affect the verdict.

```json
{
  "schema_version": 1,
  "round": 1,
  "approval": {"plan": "qa-plan-round-1-rev-1.md", "answer": "Approve"},
  "requirements": ["RC-001", "RC-002", "RC-003"],
  "scenarios": [
    {"id": "QA-001", "kind": "api", "required": true, "requirements": ["RC-001"]},
    {"id": "QA-002", "kind": "cli", "required": true, "requirements": ["RC-002"]},
    {"id": "QA-003", "kind": "ci", "required": true, "requirements": ["RC-003"]},
    {"id": "QA-004", "kind": "browser", "required": true, "requirements": ["RC-002"], "recording_required": true}
  ],
  "results": [
    {"id": "QA-001", "status": "PASS", "evidence": "evidence/QA-001-api.json"},
    {"id": "QA-002", "status": "PASS", "evidence": "evidence/QA-002-cli.txt"},
    {"id": "QA-003", "status": "INCOMPLETE", "reason": "The matching job log is unavailable"},
    {"id": "QA-004", "status": "PASS", "evidence": "evidence/round-1/QA-004-steps.md", "attempt": 1,
     "recording": "evidence/round-1/QA-004-attempt-1.webm.capture/QA-004-attempt-1.webm"}
  ]
}
```

`browser`, `mobile`, `desktop`, `api`, `cli` and `ci` use the same gate. An optional `verified_requirements` object can map an
RC ID to already-current evidence when that evidence covers every acceptance condition for that RC.

Save the command's JSON output with the round. Exit `1` means a required scenario failed. Exit `2` means
a required result, evidence, approval or coverage is incomplete, or the gate input is invalid. Exit `0` means
the recorded outcomes, evidence files, approval and coverage allow the stage to proceed. With a `SKIPPED`
approval, confirm the approval in the report. Check confirmed blockers before recording the stage verdict.
