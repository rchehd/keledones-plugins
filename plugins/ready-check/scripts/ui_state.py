import hashlib
import json
import re
import secrets
from pathlib import Path

import settings
from fingerprint import work_fingerprint
from project import BASE, ensure_excluded, migrate, migration_lock, redirected, toplevel, write_json
from reports import branch_name, prepare


VIEWS = ("qa-plan", "qa-results", "review", "settings", "reflect")
PREFERENCES = ("browser", "remind", "captureTasks", "phpstormMcp")
ASSET_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4",
               ".webm": "video/webm", ".txt": "text/plain", ".log": "text/plain"}
TRIAGE = ("fix", "accept-risk", "false-positive", "out-of-scope")
IDE_STATUSES = ("unverified", "available", "unavailable")
COMMON = ("locale", "title", "round", "status", "coverage", "limitations")
DETAILS = ("id", "title", "role", "risk", "requirements", "steps", "expected")
VIEW_FIELDS = {
    "qa-plan": ("scenarios", "qa_plan_revision", "requirements_revision", "charter"),
    "qa-results": ("scenarios",),
    "review": ("findings", "reviewed_source", "requirements_revision"),
}
ROW_FIELDS = {
    "qa-plan": ("required", "required_reason", "recording", "recording_required", "evidence",
                "environment", "preconditions", "execution", "test_data", "cleanup", "recording_scope"),
    "qa-results": ("status", "actual", "artifacts", "elapsed", "classification"),
    "review": ("description", "severity", "source", "file", "line", "snippet", "blocking"),
}


def object_at(path):
    if redirected(path) or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError(f"Expected a local JSON object at {path.name}")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


def indexed(rows, pattern):
    if not isinstance(rows, list):
        raise ValueError("Expected an array of rows")
    items = {}
    for row in rows:
        identifier = row.get("id") if isinstance(row, dict) else None
        if not isinstance(identifier, str) or not re.fullmatch(pattern, identifier) or identifier in items:
            raise ValueError("Row IDs must be valid and unique")
        items[identifier] = row
    return items


def identity(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def positive_number(value):
    return type(value) is int and value > 0


def reviewed_source(root):
    return dict(schema_version=1, branch=branch_name(root), fingerprint=work_fingerprint(root))


class View:
    def __init__(self, project, task, kind, ide_status="unverified", tasks=10, locale="en", snapshot=None):
        project = Path(project).resolve(strict=True)
        self.root = toplevel(project)
        if not self.root or not project.is_dir() or kind not in VIEWS or ide_status not in IDE_STATUSES:
            raise ValueError("A Git project and a supported view are required")
        self.kind = kind
        self.task = task
        self.ide_status = ide_status
        self.phpstorm_request = self.root / BASE / settings.PHPSTORM_REQUEST
        self.directory = None
        if kind == "reflect":
            from reflect_collect import collect, dashboard, read_snapshot

            if not positive_number(tasks) or locale not in {"en", "uk"}:
                raise ValueError("Reflect needs a positive task count and a supported display language")
            digest = read_snapshot(self.root, snapshot) if snapshot is not None else collect(self.root, tasks)
            self.reflect_data = dashboard(digest, locale)
        if kind not in {"settings", "reflect"}:
            if not task:
                raise ValueError("A task ID is required for this view")
            target = prepare(project, task, dry_run=True)
            self.directory = Path(target["directory"])
            if (target["task_id"] != task or not self.directory.is_relative_to(self.root / BASE / "reports")
                    or not self.directory.is_dir() or redirected(self.directory)):
                raise ValueError("The report must already exist in the current branch's Ready Check storage")
            self.view_file = self.directory / f"ui-{kind}.json"

    def path(self, name):
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name
                or Path(name).is_absolute() or Path(name).as_posix() != name):
            raise ValueError("Expected a path relative to the report")
        current = self.directory
        for part in Path(name).parts:
            if part == "..":
                raise ValueError("The path must stay inside the report")
            current = current / part
            if redirected(current):
                raise ValueError("Report paths must use real files and directories")
        return current

    def prepare(self, name):
        if not self.directory:
            raise ValueError("This view reads existing project data without preparation")
        data = object_at(self.path(name))
        if not positive_number(data.get("round")):
            raise ValueError("A positive round is required")
        if self.kind == "review":
            indexed(data.get("findings"), r"F-\d{3,}")
            if "reviewed_source" not in data:
                raise ValueError("The findings need the source snapshot captured before inspection.")
            if not positive_number(data.get("requirements_revision")):
                raise ValueError("The findings need the requirements revision reviewed.")
        else:
            indexed(data.get("scenarios"), r"QA-\d{3,}")
        if self.kind == "qa-plan":
            if not all(positive_number(data.get(key)) for key in ("qa_plan_revision", "requirements_revision")):
                raise ValueError("Both the plan and requirements revisions are required")
            for row in data["scenarios"]:
                if type(row.get("required")) is not bool:
                    raise ValueError("Every scenario must declare whether it is required")
                if row.get("recording_required") and not row.get("recording"):
                    raise ValueError("A mandatory recording requires a recording description")
        if self.kind == "qa-results":
            for row in data["scenarios"]:
                for asset in row.get("artifacts", []):
                    self.artifact_path(asset["path"])

        data = {key: data[key] for key in (*COMMON, *VIEW_FIELDS[self.kind]) if key in data}
        row_key = "findings" if self.kind == "review" else "scenarios"
        data[row_key] = [{key: row[key] for key in (*DETAILS, *ROW_FIELDS[self.kind]) if key in row}
                         for row in data[row_key]]
        if self.kind == "qa-results":
            for row in data[row_key]:
                row["artifacts"] = [{key: asset[key] for key in ("path", "title", "chapters") if key in asset}
                                    for asset in row.get("artifacts", [])]

        with migration_lock(self.directory):
            self.check_freshness(data)
            write_json(self.view_file, data, self.root)
        return self.current()

    def check_freshness(self, data):
        if self.kind == "review":
            if data.get("reviewed_source") != reviewed_source(self.root):
                raise ValueError("The review source snapshot is stale. Refresh the findings before using this view.")
            fields = [("requirements_revision", "Requirements revision")]
        elif self.kind == "qa-plan":
            fields = [("requirements_revision", "Requirements revision"), ("qa_plan_revision", "QA plan revision")]
        else:
            return
        report = self.path("report.md")
        if not report.is_file():
            raise ValueError("Save the task report and its current revisions before opening this view.")
        text = report.read_text(encoding="utf-8-sig")
        for key, label in fields:
            revisions = re.findall(rf"^{label}:[ \t]*([1-9][0-9]*)[ \t]*$", text, re.MULTILINE)
            if len(revisions) != 1 or not positive_number(data.get(key)):
                raise ValueError(f"The task report and view must record the current {label}.")
            if revisions[0] != str(data[key]):
                raise ValueError(f"{label} changed. Refresh this view before using it.")

    def current(self, expected_revision=None):
        if self.kind == "reflect":
            data = self.reflect_data
        elif self.kind == "settings":
            values = settings.load(self.root)
            data = {key: values[key] for key in PREFERENCES}
            data["ideStatus"] = self.ide_status
            pending = settings.pending_phpstorm_request(self.root) if not data["phpstormMcp"] else None
            data["phpstormPending"] = bool(pending)
            if pending:
                data["phpstormRequestId"] = pending["request_id"]
        else:
            data = object_at(self.view_file)
            self.check_freshness(data)
        revision = identity(data)
        if expected_revision is not None and expected_revision != revision:
            raise ValueError("This view is out of date. Open the current round or revision.")
        return dict(view=self.kind, task=self.task, revision=revision, data=data)

    def artifact_path(self, name):
        path = self.path(name)
        if (not path.is_relative_to(self.directory / "evidence") or not path.is_file()
                or path.suffix.lower() not in ASSET_TYPES):
            raise ValueError("Expected a supported local evidence file")
        return path

    def artifact(self, name, revision):
        if self.kind != "qa-results":
            raise ValueError("Artifacts belong to a QA results view")
        cases = self.current(revision)["data"]["scenarios"]
        if not any(asset["path"] == name for case in cases for asset in case.get("artifacts", [])):
            raise ValueError("Artifact is not listed in this round")
        path = self.artifact_path(name)
        return path, ASSET_TYPES[path.suffix.lower()]

    def decision(self, current=None):
        if self.kind == "reflect":
            return None
        current = current or self.current()
        if self.kind == "settings":
            pending = settings.pending_phpstorm_request(self.root)
            return pending if pending and pending["request_id"] == current["data"].get("phpstormRequestId") else None
        return self.read_decision(current["revision"])

    def read_decision(self, revision):
        path = self.decision_path(revision)
        if not path.exists():
            return None
        decision = object_at(path)
        if (decision["revision"] != revision or decision["view"] != self.kind
                or decision["task"] != self.task):
            return None
        if self.kind == "qa-results":
            return dict(decision, actions=gallery_actions(decision))
        return decision

    def previous_gallery_decisions(self, current):
        prefix = "ui-qa-results-decision-"
        decisions = []
        for path in self.directory.glob(prefix + "*.json"):
            revision = path.stem.removeprefix(prefix)
            if revision == current["revision"] or not re.fullmatch(r"[a-f0-9]{64}", revision):
                continue
            decision = self.read_decision(revision)
            if decision:
                decisions.append(decision)
        return sorted(decisions, key=lambda decision: (decision["round"], decision["revision"]))

    def decision_path(self, revision):
        return self.directory / f"ui-{self.kind}-decision-{revision}.json"

    def submit(self, request):
        if self.kind == "reflect":
            raise ValueError("The Reflect overview is read-only")
        if not isinstance(request, dict):
            raise ValueError("Expected a decision object")
        if self.kind == "settings":
            return self.submit_settings(request)

        with migration_lock(self.directory):
            current = self.current()
            if request.get("revision") != current["revision"]:
                raise ValueError("This view is out of date. Open the current round or revision.")
            decision = self.validate(request, current["data"])
            decision.update(view=self.kind, task=self.task, revision=current["revision"], round=current["data"]["round"])
            previous = self.decision(current)
            path = self.decision_path(current["revision"])
            if self.kind == "qa-results":
                return self.save_gallery_action(path, decision, previous)
            if self.kind == "review":
                decision["reviewed_source"] = current["data"]["reviewed_source"]
                decision["requirements_revision"] = current["data"]["requirements_revision"]
            if previous and previous != decision:
                raise ValueError("A decision already exists for this revision")
            if not previous:
                write_json(path, decision, self.root)
            return decision

    def submit_settings(self, request):
        if request.get("action") == "connect-phpstorm":
            migrate(self.root)
            ensure_excluded(self.root)
            with migration_lock(self.phpstorm_request.parent):
                current = self.current()
                if request.get("revision") != current["revision"]:
                    raise ValueError("Settings changed. Refresh the view.")
                if not current["data"]["phpstormMcp"] and not current["data"]["phpstormPending"]:
                    write_json(self.phpstorm_request, dict(view="settings", action="connect-phpstorm",
                                                          request_id=secrets.token_urlsafe(24)), self.root)
            return self.current()
        current = self.current()
        if request.get("revision") != current["revision"]:
            raise ValueError("Settings changed. Refresh the view.")
        key = request.get("key")
        if request.get("action") != "set" or key not in PREFERENCES:
            raise ValueError("Unsupported setting")
        value = request.get("value")
        if key == "phpstormMcp" and value is not False:
            raise ValueError("Use a connection request to enable PhpStorm from settings.")
        request_id = current["data"].get("phpstormRequestId") if key == "phpstormMcp" else None
        settings.store(key, value, self.root, phpstorm_request_id=request_id)
        return self.current()

    def save_gallery_action(self, path, decision, previous):
        additions = gallery_actions(decision)
        existing = {action["id"]: action for action in gallery_actions(previous or {})}
        for action in additions:
            if action["id"] in existing and existing[action["id"]] != action:
                raise ValueError("An action is already recorded for this scenario")
        combined = dict(existing)
        combined.update((action["id"], action) for action in additions)
        if combined != existing:
            record = {key: decision[key] for key in ("view", "task", "revision", "round")}
            write_json(path, dict(record, actions=list(combined.values())), self.root)
        return decision

    def validate(self, request, data):
        action = request.get("action")
        if self.kind == "qa-plan":
            decision = self.plan_decision(action, request, data)
            return dict(decision, qa_plan_revision=data["qa_plan_revision"],
                        requirements_revision=data["requirements_revision"])
        if self.kind == "qa-results":
            cases = indexed(data["scenarios"], r"QA-\d{3,}")
            ids = request.get("selected")
            if action not in {"retest", "draft", "false-positive"} or not valid_ids(ids, cases) or not ids:
                raise ValueError("Select a result and a supported action")
            return dict(action=action, selected=ids, reason=note(request.get("reason", ""), action == "false-positive"))

        findings = indexed(data["findings"], r"F-\d{3,}")
        rows = indexed(request.get("rows"), r"F-\d{3,}")
        if action != "triage" or not rows or not rows.keys() <= findings.keys():
            raise ValueError("Choose an action for one or more findings")
        decisions = []
        for identifier, row in rows.items():
            choice = row.get("action")
            if choice not in TRIAGE:
                raise ValueError("Unsupported review action")
            decisions.append(dict(id=identifier, action=choice,
                                  reason=note(row.get("reason", ""), choice != "fix")))
            source = findings[identifier].get("source")
            if isinstance(source, str) and source:
                decisions[-1]["source"] = source
        return dict(action=action, rows=decisions)

    def plan_decision(self, action, request, data):
        cases = indexed(data["scenarios"], r"QA-\d{3,}")
        if action == "approve":
            selected, recordings = request.get("selected"), request.get("recordings")
            if not valid_ids(selected, cases) or not valid_ids(recordings, cases):
                raise ValueError("Scenario and recording selections must use current scenario IDs")
            required = {key for key, value in cases.items() if value["required"]}
            planned = {key for key in selected if cases[key].get("recording")}
            mandatory = {key for key in planned if cases[key].get("recording_required")}
            if not required <= set(selected) or not mandatory <= set(recordings) <= planned:
                raise ValueError("Select every required scenario and mandatory recording")
            return dict(action=action, selected=selected, recordings=recordings)
        if action == "revise":
            edits = request.get("edits", {})
            if not isinstance(edits, dict) or not edits.keys() <= cases.keys():
                raise ValueError("Edits must target current scenarios")
            revised = {key: note(value, True) for key, value in edits.items()}
            additions = note(request.get("additions", ""))
            charter = note(request["charter"]) if "charter" in request else None
            if not revised and not additions and charter is None:
                raise ValueError("Enter at least one change")
            return dict(action=action, edits=revised, additions=additions, charter=charter)
        if action == "cancel":
            return dict(action=action)
        raise ValueError("Choose a supported QA plan action")


def valid_ids(values, choices):
    return (isinstance(values, list) and all(isinstance(value, str) and value in choices for value in values)
            and len(values) == len(set(values)))


def gallery_actions(decision):
    if "actions" in decision:
        return decision["actions"]
    return [dict(id=f"{decision['action']}:{scenario}", action=decision["action"],
                 scenario=scenario, reason=decision.get("reason", ""))
            for scenario in decision.get("selected", [])]


def note(value, required=False):
    if not isinstance(value, str) or len(value) > 4_000 or required and not value.strip():
        raise ValueError("Enter a reason or note of up to 4,000 characters")
    return value.strip()
