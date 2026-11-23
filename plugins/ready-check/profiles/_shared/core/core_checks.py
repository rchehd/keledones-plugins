import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_support import execute
from core_scope import DATA
from core_toolchain import JS, STYLES

TEMP = DATA + "/tmp"
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? ")


def changed_lines(diff):
    lines, line, replacing = [], 0, False

    for row in (diff or "").splitlines():
        match = HUNK.match(row)

        if match:
            # "-N,0" inserts after line N, so the next old line is N + 1.
            line, replacing = int(match[1]) + (match[2] == "0"), False
        elif row.startswith("-") and line:
            lines.append(line)
            line, replacing = line + 1, True
        elif row.startswith("+") and line:
            # Added rows that replace removed rows are already covered by those rows.
            if not replacing:
                lines += [n for n in (line - 1, line) if n and n not in lines]
        elif row.startswith(" ") and line:
            line, replacing = line + 1, False

    return lines


def format_line(lint, name, diff):
    relative = lint.relative(name)

    if relative not in lint.lines:
        return None

    scope = lint.lines[relative]
    changed = changed_lines(diff)

    if not changed:
        rows = [row for row in (diff or "").splitlines() if row[:1] in "+-" and row[:3] not in ("+++", "---")]
        # A missing diff or one without numbered hunks has no position, so the file is reported at line 0 as before.
        return 0 if rows or not diff else None

    found = [n for n in changed if scope is None or n in scope]

    return found[0] if found else None


def checkstyle_report(lint, raw):
    reported = False
    tree = ET.fromstring(raw[raw.index("<"):].strip())

    if tree.tag != "checkstyle":
        raise ValueError("Expected a checkstyle report")

    for file in tree.iter("file"):
        for item in file.iter("error"):
            reported = True
            lint.add(file.get("name"), item.get("line"), item.get("message", ""), item.get("severity", "error"), item.get("source"), True)
    return reported


def eslint_report(lint, data):
    reported = False

    if not isinstance(data, list):
        raise ValueError("Expected an array")

    for entry in data:
        for item in entry["messages"]:
            reported = True
            fatal = item.get("fatal") and lint.relative(entry["filePath"]) in lint.lines
            lint.add(entry["filePath"], item.get("line"), item["message"], "error" if item["severity"] == 2 else "warning",
                     item.get("ruleId") or item.get("rule") or "eslint", not fatal)
    return reported


def stylelint_report(lint, data):
    reported = False

    if not isinstance(data, list):
        raise ValueError("Expected an array")

    for entry in data:
        for item in entry.get("warnings", []):
            reported = True
            fatal = item.get("rule") == "CssSyntaxError" and lint.relative(entry["source"]) in lint.lines
            lint.add(entry["source"], item.get("line"), item["text"], item.get("severity", "error"),
                     item.get("ruleId") or item.get("rule") or "stylelint", not fatal)

        for item in entry.get("parseErrors", []):
            reported = True
            lint.add(entry["source"], item.get("line"), item.get("text", "Parse error"))
    return reported


def dup_report(lint, data):
    reported = False

    for item in data["duplicates"]:
        reported = True
        a, b = item["firstFile"], item["secondFile"]

        for x, y in ((a, b), (b, a)):
            file = lint.relative(x["name"])

            if file in lint.lines and (lint.lines[file] is None or any(n in lint.lines[file] for n in range(x["start"], x["end"] + 1))):
                lint.add(file, x["start"], f"{item['lines']} lines duplicate {lint.relative(y['name'])}:{y['start']}-{y['end']}", "warning")
                break
    return reported


Parser = namedtuple("Parser", "codes opener handle")
Provider = namedtuple("Provider", "directory applies claims plan checks parsers")
CORE_PARSERS = {"checkstyle": Parser({0, 1}, None, checkstyle_report), "eslint": Parser({0, 1}, "[", eslint_report),
                "stylelint": Parser({0, 2}, "[", stylelint_report), "dup": Parser({0, 1}, "{", dup_report)}
CORE_CHECKS = {"debug", "diff", "js", "dup"}


class Lint:
    def __init__(self, check, project, runner, evidence, timeout, selected, files, lines, merge, spec):
        self.check, self.project, self.runner, self.spec = check, project, runner, spec
        self.evidence, self.timeout, self.selected = evidence, timeout, selected
        self.files, self.lines, self.merge = files, lines, merge
        self.findings, self.incomplete, self.na = [], [], None
        self.details = {}
        self.log = evidence / (check + ".log")
        self.log.write_bytes(b"")
        self._custom = None
        self.parsers = dict(CORE_PARSERS)

        for provider in getattr(spec, "providers", ()):
            self.parsers.update(provider.parsers)
        self.parsers.update(getattr(spec, "parsers", {}))

    @property
    def custom(self):
        if self._custom is None:
            self._custom = []
            custom = self.spec.custom_code

            if custom.get("paths"):
                self._custom = [p for p in custom["paths"] if (self.project / p).is_dir()]
                return self._custom

            for directory, children, _ in os.walk(self.project):
                children[:] = [n for n in children if n not in self.spec.excluded and n not in {".git", *custom["skip"]}]
                path = Path(directory)

                if path.name == custom["name"] and path.parent.name in custom["parents"]:
                    self._custom.append(path.relative_to(self.project).as_posix())
                    children[:] = []
        return self._custom

    def relative(self, file):
        value = str(file).replace("\\", "/")

        for root in (self.runner.root, str(self.project)):
            prefix = root.replace("\\", "/").rstrip("/") + "/"
            matches = value.lower().startswith(prefix.lower()) if os.name == "nt" else value.startswith(prefix)

            if matches:
                return value[len(prefix):]
        return value.removeprefix("./")

    def add(self, file, line, message, severity="error", source=None, filter_lines=False):
        file = self.relative(file)
        line = int(line or 0)

        if filter_lines and (file not in self.lines or self.lines[file] is not None and line not in self.lines[file]):
            return
        self.findings.append(dict(file=file, line=line, message=message, severity=severity.lower(), source=source or self.check))

    def call(self, argv, env=None, host=False, cwd=None):
        code, stdout, stderr = (execute(argv, cwd or self.project, self.timeout, env=None) if host else
                                self.runner.exec(argv, self.timeout, env=env, cwd=cwd))
        with self.log.open("ab") as stream:
            stream.write(json.dumps(list(map(str, argv)), ensure_ascii=False).encode() + b"\n" + stdout + b"\n" + stderr + b"\n")
        return code, stdout, stderr

    def parse(self, tool, code, stdout, stderr=b"", label=None):
        reported = False
        raw = (stdout + b"\n" + stderr).decode(errors="replace")
        try:
            parser = self.parsers[tool]

            if code not in parser.codes:
                raise ValueError(f"Unexpected exit code {code}")

            if parser.opener:
                data, _ = json.JSONDecoder().raw_decode(raw[raw.index(parser.opener):])
            else:
                data = raw
            reported = parser.handle(self, data)

            if code and not reported:
                raise ValueError(f"Exit code {code} without reported findings")
        except (ValueError, TypeError, KeyError, AttributeError, ET.ParseError) as error:
            self.incomplete.append(f"{label or tool} did not produce a usable report: {error}; see log")

    def temporary(self, name, content):
        path = self.temp / name
        path.write_text(content, encoding="utf-8")
        return self.temporary_path(name)

    def temporary_path(self, name):
        return str(self.temp / name) if self.runner.name == "local" else self.runner.path(TEMP, self.temp.name, name)

    def binary(self, name):
        return next(t["path"] for t in self.selected["tools"] if t["name"] == name)

    def provided(self):
        checks = {}

        for provider in getattr(self.spec, "providers", ()):
            checks.update(provider.checks)

        if self.check not in checks:
            raise ValueError(f"Check {self.check} is not implemented by this profile")

        return checks

    def run(self):
        location = self.evidence if self.runner.name == "local" else self.project / TEMP

        if self.runner.name != "local":
            current = self.project

            for part in Path(TEMP).parts:
                current = current / part

                if current.is_symlink() or current.exists() and not current.is_dir():
                    raise ValueError(f"Temporary data path must contain real directories: {current}")
                current.mkdir(exist_ok=True)
        else:
            location.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".ready-check-lint.", dir=location) as folder:
            self.temp = Path(folder)
            extra = self.spec.extra_checks.get(self.check)

            if extra:
                extra.run(self)
            elif self.check in CORE_CHECKS:
                getattr(self, self.check)()
            else:
                self.provided()[self.check](self)
        status = "N/A" if self.na else "INCOMPLETE" if self.incomplete else "FAIL" if any(f["severity"] == "error" for f in self.findings) else "PASS"
        return dict(status=status, findings=self.findings, reason=self.na or "; ".join(self.incomplete) or None,
                    evidence=[str(self.log)], **self.details)

    def debug(self):
        matcher = getattr(self.spec, "debug_match", None)

        for file in self.files:
            if Path(file).suffix not in JS | self.spec.code_extensions:
                continue

            for number, text in enumerate((self.project / file).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if matcher(file, text) if matcher else self.spec.debug_pattern.search(text):
                    self.add(file, number, text.strip(), filter_lines=True)

    def diff(self):
        empty = self.temp / "empty"
        empty.touch()

        for file in self.files:
            if Path(file).suffix in {".md", ".diff", ".patch"}:
                continue
            tracked = self.merge and self.lines[file] is not None
            args = (["git", "-c", "core.quotepath=false", "diff", "--no-ext-diff", "--no-textconv", "--check", self.merge, "--", file]
                    if tracked else ["git", "-c", "core.quotepath=false", "diff", "--no-index", "--check", "--", str(empty), file])
            code, stdout, stderr = self.call(args, host=True)

            if code not in {0, 1, 2, 3} or stderr and b"fatal:" in stderr:
                raise ValueError("Git whitespace check did not complete; see log")
            matched = False

            for row in stdout.decode(encoding="utf-8", errors="replace").splitlines():
                match = re.match(r"^(?!\+).*?:(\d+): (.+)", row)

                if match:
                    matched = True
                    self.add(file, match[1], match[2], filter_lines=not self.merge)

            if code in {2, 3} and not matched:
                raise ValueError("Git whitespace check failed without a usable finding; see log")

    def js(self):
        env = self.selected["environment"]

        for tool, extensions in (("eslint", JS), ("stylelint", STYLES)):
            files = [self.runner.path(f) for f in self.files if Path(f).suffix in extensions]

            if not files:
                continue
            prefix = "LINT_" + tool.upper()
            args = [env[prefix + "_BIN"], "--config", env[prefix + "_CONFIG"]]
            environment = {}

            if tool == "eslint":
                args += ["--format", "json"]

                if env.get("LINT_ESLINT_LEGACY"):
                    environment["ESLINT_USE_FLAT_CONFIG"] = "false"
                else:
                    args += ["--no-warn-ignored"]
            else:
                args += ["--allow-empty-input", "--formatter", "json"]
            self.parse(tool, *self.call([*args, *files], env=environment))

    def dup(self):
        if not self.custom:
            raise ValueError("Duplication analysis needs an agreed custom-code directory")
        env = self.selected["environment"]
        host = env.get("LINT_JSCPD_RUNNER") != "1"
        output = str(self.temp / "jscpd") if host or self.runner.name == "local" else self.runner.path(TEMP, self.temp.name, "jscpd")
        args = [env["LINT_JSCPD"], *self.custom, "-a", "-f", self.spec.dup["formats"], "--formats-exts",
                self.spec.dup["extensions"], "-i",
                "**/node_modules/**,**/dist/**,**/vendor/**,**/*.min.js,**/storybook-static/**,**/tests/fixtures/**" +
                self.spec.dup.get("ignore", ""),
                "-k", os.environ.get("LINT_DUP_TOKENS", "70"), "-l", os.environ.get("LINT_DUP_LINES", "6"), "-r", "json,silent", "-o", output]
        code, _, _ = self.call(args, host=host)
        report = self.temp / "jscpd/jscpd-report.json"
        self.parse("dup", code, report.read_bytes() if report.is_file() else b"")


def run_check(check, project, runner, evidence, timeout, selected, files, lines, merge, spec):
    return Lint(check, project, runner, evidence, timeout, selected, files, lines, merge, spec).run()
