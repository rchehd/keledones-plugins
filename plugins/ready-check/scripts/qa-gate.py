import argparse
import json
import re
import sys
from pathlib import Path

from qa_evidence import RECORDING, capture_attempt, recording_digest

KINDS = {"browser", "mobile", "desktop", "api", "cli", "ci"}
STATUSES = {"PASS", "FAIL", "INCOMPLETE", "NOT_RUN", "N/A"}
EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def ids(values, prefix):
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not re.fullmatch(prefix + r"-\d{3,}", value) for value in values
    ):
        raise ValueError(f"Expected an array of {prefix} IDs")
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {prefix} ID")
    return set(values)


def by_id(items):
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Expected an array of scenario or result objects")
    ids([item.get("id") for item in items], "QA")
    return {item["id"]: item for item in items}


def matching_recording(report, case, round_number, result):
    reference, attempt, outcome = result.get("recording"), result.get("attempt"), result.get("status")
    source_round = result.get("recorded_round", round_number)
    if (not has_text(reference) or type(attempt) is not int or attempt < 1 or outcome not in {"PASS", "FAIL"}
            or type(round_number) is not int or type(source_round) is not int or not 1 <= source_round <= round_number):
        return False
    if source_round < round_number and (outcome != "PASS" or not has_text(result.get("carry_over_reason"))):
        return False
    directory = f"evidence/round-{source_round}"
    prefix = directory + "/"
    selector = reference.removeprefix(prefix)
    if selector == reference or capture_attempt(case, selector) != attempt:
        return False
    clip = report / reference
    journal = report / directory / f"{case}-steps.md"
    try:
        if clip.resolve() != clip or journal.resolve() != journal or not journal.is_file():
            return False
        records = [entry for entry in RECORDING.finditer(journal.read_text(encoding="utf-8"))
                   if entry["attempt"] == str(attempt)]
        if {entry["outcome"] for entry in records} != {outcome}:
            return False
        digests = {entry["digest"] for entry in records if entry["video"] == selector}
        return bool(digests) and clip.is_file() and clip.stat().st_size > 0 and digests == {recording_digest(clip)}
    except (OSError, RuntimeError, ValueError):
        return False


def gate(data, report):
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Expected a QA gate object with schema_version 1")
    requirements = ids(data.get("requirements"), "RC")
    scenarios = by_id(data.get("scenarios"))
    results = by_id(data.get("results"))
    if not requirements or not scenarios:
        raise ValueError("A QA plan needs current requirements and scenarios")
    if results.keys() - scenarios.keys():
        raise ValueError("Results must refer to scenarios in the approved plan")

    verified = data.get("verified_requirements", {})
    if not isinstance(verified, dict) or verified.keys() - requirements or not all(map(has_text, verified.values())):
        raise ValueError("Existing verification needs a current requirement ID and evidence reference")

    covered = set(verified)
    round_number = data.get("round")
    failures, pending, missing_recordings, cases = [], [], [], []
    for case_id, scenario in scenarios.items():
        kind, required = scenario.get("kind"), scenario.get("required")
        if not isinstance(kind, str) or kind not in KINDS or type(required) is not bool:
            raise ValueError(f"{case_id} needs a supported kind and a boolean required field")
        recording_required = scenario.get("recording_required", False)
        if type(recording_required) is not bool or recording_required and not required:
            raise ValueError(f"{case_id} needs a boolean recording_required field, true only for required cases")
        links = ids(scenario.get("requirements"), "RC")
        if links - requirements:
            raise ValueError(f"{case_id} refers to a requirement outside the current plan")

        result = results.get(case_id, {"status": "NOT_RUN"})
        status = result.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError(f"{case_id} has an invalid result status")
        if status in {"PASS", "FAIL"} and not has_text(result.get("evidence")):
            raise ValueError(f"{case_id} needs an evidence reference for {status}")
        if status in {"INCOMPLETE", "N/A"} and not has_text(result.get("reason")):
            raise ValueError(f"{case_id} needs a reason for {status}")

        if recording_required and not matching_recording(report, case_id, round_number, result):
            missing_recordings.append(case_id)
            if status in {"PASS", "N/A"}:
                status = "INCOMPLETE"

        if status == "PASS":
            covered.update(links)
        elif required and status == "FAIL":
            failures.append(case_id)
        elif required and status in {"INCOMPLETE", "NOT_RUN"}:
            pending.append(case_id)
        cases.append(dict(id=case_id, kind=kind, required=required, status=status))

    uncovered = sorted(requirements - covered)
    if failures:
        status = "FAIL"
    elif pending or uncovered:
        status = "INCOMPLETE"
    else:
        status = "PASS"
    return dict(status=status, can_proceed=status == "PASS", failed_required=failures, pending_required=pending,
                uncovered_requirements=uncovered, missing_required_recordings=missing_recordings, scenarios=cases)


def main():
    parser = argparse.ArgumentParser(description="Evaluate QA coverage from the approved plan and current evidence.")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    output = dict(schema_version=1, action="qa-gate", status="INCOMPLETE", can_proceed=False)
    try:
        path = args.input.resolve()
        output.update(gate(json.loads(path.read_text(encoding="utf-8-sig")), path.parent))
    except (OSError, ValueError) as error:
        output["reason"] = str(error)
    print(json.dumps(output, indent=2))
    return EXIT_CODES[output["status"]]
