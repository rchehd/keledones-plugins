import json
import os
import re
import sys
from collections import namedtuple
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared/core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core_checks import Parser, format_line
import go_tools as tools

GoCheck = namedtuple("GoCheck", "applies run plan")
MODULE_FILES = {"go.mod", "go.sum"}
POSITION = re.compile(r"^(vet: )?(?:\./)?((?:[A-Za-z]:[\\/])?[^\s:][^:\r\n]*\.go):(\d+)(?::\d+)?: ([^\r\n]*)\r?$", re.M)
DIFF_FILE = re.compile(r"^--- (.+?)\.orig(?:\t[^\r\n]*)?\r?$", re.M)
WARNING = {"warning", "info"}


def go_files(paths):
    return [p for p in paths if Path(p).suffix == ".go"]


def go_applies(paths):
    return bool(go_files(paths))


def module_applies(paths):
    return go_applies(paths) or any(Path(p).name in MODULE_FILES for p in paths)


def runner_files(lint):
    return [lint.runner.path(f) for f in lint.files if f.endswith(".go")]


def packages(lint):
    folders = {PurePosixPath(f).parent.as_posix() for f in lint.files if f.endswith(".go")}

    return sorted("." if folder == "." else "./" + folder for folder in folders)


def command(lint, name):
    return next(t["path"] for t in lint.selected["tools"] if t["name"] == name)


def gofmt_report(lint, text):
    reported = False

    for match in POSITION.finditer(text):
        reported = True
        lint.add(match[2], match[3], match[4], "error", "gofmt")
    parts = DIFF_FILE.split(text)

    for name, diff in zip(parts[1::2], parts[2::2]):
        reported = True
        line = format_line(lint, name, diff)

        if line is not None:
            lint.add(name, line, "File is not formatted as gofmt would write it", "error", "gofmt")

    return reported


def vet_report(lint, text):
    reported = False

    for match in POSITION.finditer(text):
        reported = True
        lint.add(match[2], match[3], match[4], "error", "vet", filter_lines=not match[1])

    return reported


def build_report(lint, text):
    reported = False

    for match in POSITION.finditer(text):
        reported = True
        lint.add(match[2], match[3], match[4], "error", "build")

    return reported


def golangci_report(lint, data):
    reported = False

    if not isinstance(data, dict):
        raise ValueError("Expected an object")

    for item in data.get("Issues") or []:
        reported = True
        position = item.get("Pos") or {}
        severity = "warning" if str(item.get("Severity", "")).lower() in WARNING else "error"

        if item["FromLinter"] == "typecheck":
            found = list(POSITION.finditer(item["Text"]))

            for match in found:
                lint.add(match[2], match[3], match[4], "error", "typecheck")

            if found:
                continue
        lint.add(position.get("Filename", ""), position.get("Line"), item["Text"], severity, item["FromLinter"], True)

    return reported


def stream(text):
    decoder, position, items = json.JSONDecoder(), 0, []

    while True:
        start = text.find("{", position)

        if start < 0:
            break
        try:
            item, position = decoder.raw_decode(text, start)
        except ValueError:
            break
        items.append(item)

    return items


def govulncheck_report(lint, text):
    items = stream(text)

    if not any("config" in item for item in items):
        raise ValueError("Expected a govulncheck JSON stream")
    summaries = {item["osv"]["id"]: item["osv"].get("summary", "") for item in items if "osv" in item}
    seen = set()

    for item in items:
        finding = item.get("finding")
        trace = (finding or {}).get("trace") or []

        if not trace or not trace[0].get("function"):
            continue
        key = (finding["osv"], trace[0].get("module"))

        if key in seen:
            continue
        seen.add(key)
        fixed = finding.get("fixed_version") or "none"
        where = trace[-1].get("position") or {}
        message = f"{finding['osv']}: {summaries.get(finding['osv'], '')} ({trace[0].get('module')}@{trace[0].get('version')}, fixed in {fixed})"
        lint.add(where.get("filename") or "go.mod", where.get("line"), message, "warning", finding["osv"])

    return bool(seen)


PARSERS = {"gofmt": Parser({0, 1, 2}, None, gofmt_report), "vet": Parser({0, 1, 2}, None, vet_report),
           "build": Parser({0, 1}, None, build_report), "golangci": Parser({0, 1}, "{", golangci_report),
           "govulncheck": Parser({0}, None, govulncheck_report)}


def gofmt_run(lint):
    lint.parse("gofmt", *lint.call([command(lint, "gofmt"), "-d", *runner_files(lint)]))


def vet_run(lint):
    lint.parse("vet", *lint.call([command(lint, "go"), "vet", *packages(lint)]))


def build_run(lint):
    null = os.devnull if lint.runner.name == "local" else "/dev/null"
    lint.parse("build", *lint.call([command(lint, "go"), "build", "-o", null, "./..."]))


def golangci_run(lint):
    config = lint.selected["environment"]["LINT_GOLANGCI_CONFIG"]
    args = [command(lint, "golangci-lint"), "run", "--config", config, "--path-mode", "abs", "--output.json.path", "stdout",
            "--show-stats=false", "--max-issues-per-linter", "0", "--max-same-issues", "0"]
    lint.parse("golangci", *lint.call([*args, *packages(lint)]))


def govulncheck_run(lint):
    lint.parse("govulncheck", *lint.call([command(lint, "govulncheck"), "-json", "./..."]))


EXTRA = dict(
    gofmt=GoCheck(go_applies, gofmt_run, tools.plan),
    vet=GoCheck(go_applies, vet_run, tools.plan),
    golangci=GoCheck(go_applies, golangci_run, tools.plan),
    build=GoCheck(module_applies, build_run, tools.plan),
    govulncheck=GoCheck(module_applies, govulncheck_run, tools.plan))
