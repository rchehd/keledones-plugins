import re
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared/core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core_checks import TEMP, Parser
import python_tools as tools

PyCheck = namedtuple("PyCheck", "applies run plan")
REQUIREMENTS = re.compile(r"requirements[\w.-]*\.txt$")
LOCKS = {"pyproject.toml", "uv.lock", "poetry.lock", "Pipfile.lock"}
SYNTAX = ("import ast, json, sys\nout = []\nfor name in sys.argv[1:]:\n    try:\n"
          "        compile(open(name, 'rb').read(), name, 'exec', flags=ast.PyCF_ONLY_AST)\n"
          "    except SyntaxError as error:\n        out.append({'file': name, 'line': error.lineno or 0, 'message': error.msg})\n"
          "    except (ValueError, OSError) as error:\n        out.append({'file': name, 'line': 0, 'message': str(error)})\n"
          "print(json.dumps(out))\n")
DIFF_FILE = re.compile(r"^--- ([^\r\n]+?)(?:\t[^\r\n]*)?\r?$", re.M)
HUNK = re.compile(r"^@@ -(\d+)", re.M)
MYPY_LINE = re.compile(r"^(.+?):(\d+)(?::\d+)?: (error|warning): (.*)$", re.M)
DJANGO_ITEM = re.compile(r"^(\S[^:]*): \(([\w.]+)\) (.*)$")
SEVERITY = {"HIGH": "error", "MEDIUM": "warning", "LOW": "warning"}


def py_files(paths):
    return [p for p in paths if Path(p).suffix == ".py"]


def py_applies(paths):
    return bool(py_files(paths))


def audit_applies(paths):
    return any(REQUIREMENTS.match(Path(p).name) or Path(p).name in LOCKS for p in paths)


def runner_files(lint):
    return [lint.runner.path(f) for f in lint.files if f.endswith(".py")]


def command(lint, name):
    found = next(t for t in lint.selected["tools"] if t["name"] == name)
    return [found["path"], "-m", found["module"]] if "module" in found else [found["path"]]


def interpreter(lint):
    return lint.selected["environment"]["LINT_PYTHON"]


def ruff_args(lint):
    config = lint.selected["environment"].get("LINT_RUFF_CONFIG")
    return ["--config", config] if config else ["--force-exclude"]


def ruff_report(lint, data):
    reported = False

    if not isinstance(data, list):
        raise ValueError("Expected an array")

    for item in data:
        reported = True
        lint.add(item["filename"], (item.get("location") or {}).get("row"), item["message"], "error", item.get("code") or "ruff", True)

    return reported


def first_change(diff):
    match = HUNK.search(diff)

    if not match:
        return 0
    line = int(match[1])

    for row in diff[match.end():].splitlines()[1:]:
        if row.startswith(("+", "-")):
            return line
        line += 1

    return int(match[1])


def format_report(lint, text):
    reported = False
    parts = DIFF_FILE.split(text)

    for name, diff in zip(parts[1::2], parts[2::2]):
        reported = True
        lint.add(name, first_change(diff), "File is not formatted as ruff format would write it", "error", "format")

    return reported


def syntax_report(lint, data):
    for item in data:
        lint.add(item["file"], item["line"], item["message"], "error", "syntax")

    return bool(data)


def mypy_report(lint, text):
    reported = False

    for match in MYPY_LINE.finditer(text):
        reported = True
        lint.add(match[1], match[2], match[4], match[3], "mypy", True)

    return reported


def django_report(lint, text):
    if "Traceback" in text or "System check identified" not in text:
        raise ValueError("manage.py did not complete the system check")
    reported, severity = False, "warning"

    for row in text.splitlines():
        header = re.match(r"^(CRITICALS|ERRORS|WARNINGS|INFOS|DEBUGS):$", row)
        item = DJANGO_ITEM.match(row)

        if header:
            severity = "error" if header[1] in {"CRITICALS", "ERRORS"} else "warning"
        elif item and not row.startswith("System check"):
            reported = True
            lint.add("manage.py", 0, f"{item[1]}: {item[3]}", severity, item[2])

    return reported


def migrations_report(lint, text):
    if "Traceback" in text:
        raise ValueError("manage.py did not complete makemigrations")

    if "Conflicting migrations" in text:
        lint.add("manage.py", 0, "Conflicting migrations detected; merge them", "error", "migrations")
        return True
    reported, inside, target, operations = False, False, None, []

    for row in text.splitlines() + ["Migrations for '':"]:
        header = re.match(r"^Migrations for '(.*)':", row)

        if header:
            if target:
                lint.add(target, 0, "Model changes have no migration: " + "; ".join(operations), "error", "migrations")
            inside, target, operations = True, None, []
        elif inside and target is None and row.startswith("  ") and row.strip():
            target, reported = row.strip(), True
        elif target and row.startswith("    "):
            operations.append(row.strip())

    return reported


def bandit_report(lint, data):
    reported = False

    if data.get("errors"):
        raise ValueError("; ".join(str(e) for e in data["errors"]))

    for item in data["results"]:
        reported = True
        lint.add(item["filename"], item.get("line_number"), f"{item['issue_text']} ({item.get('test_name', '')})",
                 SEVERITY.get(str(item.get("issue_severity")).upper(), "warning"), item.get("test_id") or "bandit", True)

    return reported


def audit_report(lint, data):
    reported = False

    for dependency in data["dependencies"]:
        for vulnerability in dependency.get("vulns", []):
            reported = True
            fixes = ", ".join(vulnerability.get("fix_versions") or []) or "none"
            lint.add(lint.target, 0, f"{dependency['name']} {dependency['version']}: {vulnerability['id']} (fixed in {fixes})",
                     "warning", vulnerability["id"])

    return reported


PARSERS = {"ruff": Parser({0, 1}, "[", ruff_report), "format": Parser({0, 1}, None, format_report),
           "pysyntax": Parser({0}, "[", syntax_report), "mypy": Parser({0, 1}, None, mypy_report),
           "django": Parser({0, 1}, None, django_report), "migrations": Parser({0, 1}, None, migrations_report),
           "bandit": Parser({0, 1}, "{", bandit_report), "audit": Parser({0, 1}, "{", audit_report)}


def ruff_run(lint):
    args = [*command(lint, "ruff"), "check", "--output-format=json", "--no-cache", *ruff_args(lint)]
    lint.parse("ruff", *lint.call([*args, *runner_files(lint)]))


def format_run(lint):
    args = [*command(lint, "ruff"), "format", "--check", "--diff", "--no-cache", *ruff_args(lint)]
    lint.parse("format", *lint.call([*args, *runner_files(lint)], env={"NO_COLOR": "1"}))


def syntax_run(lint):
    lint.parse("pysyntax", *lint.call([*interpreter(lint), "-c", SYNTAX, *runner_files(lint)], env={"PYTHONDONTWRITEBYTECODE": "1"}))


def mypy_run(lint):
    if not tools.mypy_configured(lint.project):
        lint.na = "mypy is not configured by the project ([tool.mypy], mypy.ini or setup.cfg)"
        return
    cache = str(lint.temp / "mypy") if lint.runner.name == "local" else lint.runner.path(TEMP, lint.temp.name, "mypy")
    args = [*command(lint, "mypy"), "--show-column-numbers", "--no-error-summary", "--no-color-output", "--no-pretty",
            "--hide-error-context", "--cache-dir", cache]
    executable = lint.selected["environment"].get("LINT_MYPY_PYTHON")

    if executable:
        args += ["--python-executable", executable]
    lint.parse("mypy", *lint.call([*args, *runner_files(lint)]))


def manage(lint, *args, parser):
    if not tools.django_project(lint.project):
        lint.na = "Not a Django project (no manage.py)"
        return
    command = [*interpreter(lint), "manage.py", *args]
    lint.parse(parser, *lint.call(command, env={"PYTHONDONTWRITEBYTECODE": "1"}))


def django_run(lint):
    manage(lint, "check", parser="django")


def migrations_run(lint):
    manage(lint, "makemigrations", "--check", "--dry-run", "--no-input", parser="migrations")


def bandit_run(lint):
    args = [*command(lint, "bandit"), "-f", "json", "-q"]

    if tools.bandit_configured(lint.project):
        args += ["-c", lint.runner.path("pyproject.toml")]
    else:
        args += ["--skip", "B101"]
    lint.parse("bandit", *lint.call([*args, *runner_files(lint)]))


def audit_run(lint):
    names = [f for f in lint.files if REQUIREMENTS.match(Path(f).name)]
    targets = names or [f for f in lint.files if Path(f).name in LOCKS][:1]

    if not targets:
        lint.na = "No dependency file in this diff"
        return

    for target in targets:
        lint.target = target
        scope = ["-r", lint.runner.path(target)] if target in names else [lint.runner.root]
        lint.parse("audit", *lint.call([*command(lint, "pip-audit"), "-f", "json", "--progress-spinner", "off", *scope]), label="pip-audit " + target)


EXTRA = dict(
    ruff=PyCheck(py_applies, ruff_run, tools.plan),
    format=PyCheck(py_applies, format_run, tools.plan),
    syntax=PyCheck(py_applies, syntax_run, tools.plan),
    mypy=PyCheck(py_applies, mypy_run, tools.plan),
    django=PyCheck(py_applies, django_run, tools.plan),
    migrations=PyCheck(py_applies, migrations_run, tools.plan),
    bandit=PyCheck(py_applies, bandit_run, tools.plan),
    audit=PyCheck(audit_applies, audit_run, tools.plan))
