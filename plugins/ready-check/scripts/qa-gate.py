import argparse
import json
import re
import sys
from pathlib import Path

KINDS = {"browser", "api", "cli", "ci"}
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


def gate(data):
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
    failures, pending, cases = [], [], []
    for case_id, scenario in scenarios.items():
        kind, required = scenario.get("kind"), scenario.get("required")
        if not isinstance(kind, str) or kind not in KINDS or type(required) is not bool:
            raise ValueError(f"{case_id} needs a supported kind and a boolean required field")
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
                uncovered_requirements=uncovered, scenarios=cases)


def main():
    parser = argparse.ArgumentParser(description="Evaluate QA coverage from the approved plan and current evidence.")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    output = dict(schema_version=1, action="qa-gate", status="INCOMPLETE", can_proceed=False)
    try:
        output.update(gate(json.loads(args.input.read_text(encoding="utf-8-sig"))))
    except (OSError, ValueError) as error:
        output["reason"] = str(error)
    print(json.dumps(output, indent=2))
    return EXIT_CODES[output["status"]]
