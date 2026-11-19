import json
import os
import re
from codecs import BOM_UTF8
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from process_support import find_command
from yaml_checks import is_yaml, yaml_plan, yaml_run


SHELLS = {"sh", "bash"}
SHELL_EXTENSIONS = {".sh", ".bash"}
SHELL_LINE = re.compile(r":\s*(?:line\s+)?(\d+):")


def syntax_type(path):
    if path.suffix == ".py":
        return "python"
    if (path.suffix == ".json" and not {".vscode", ".devcontainer"} & set(path.parts)
            and path.name.split(".", 1)[0] not in {"tsconfig", "jsconfig"} and path.name != "devcontainer.json"):
        return "json"
    return None


def reject_json_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def syntax_run(lint):
    for file in lint.files:
        file_type = syntax_type(Path(file))
        if not file_type:
            continue
        source = (lint.project / file).read_bytes()
        try:
            if file_type == "python":
                compile(source, file, "exec", dont_inherit=True)
            else:
                json.loads(source, parse_constant=reject_json_constant)
        except (ValueError, SyntaxError) as error:
            lint.add(file, getattr(error, "lineno", 0), getattr(error, "msg", str(error)), source=file_type)


def script_shell(path):
    with path.open("rb") as stream:
        first = stream.readline(512)
    if first.startswith(BOM_UTF8 + b"#!"):
        return None, "Remove the UTF-8 BOM so the shebang starts at the first byte of the file."
    if not first.startswith(b"#!"):
        return ("bash" if path.suffix == ".bash" else "sh"), None
    words = first[2:].decode("utf-8", errors="replace").split()
    if words and PurePosixPath(words[0]).name == "env":
        words = [word for word in words[1:] if not word.startswith("-") and "=" not in word]
    name = PurePosixPath(words[0]).name if words else None
    return (name if name in SHELLS else None), None


def local_shell(name):
    if os.name != "nt":
        return find_command(name)
    git = find_command("git")
    if git:
        for directory in Path(git).resolve().parents:
            shell = directory / "bin" / f"{name}.exe"
            if shell.is_file():
                return str(shell)
    return None


def shell_plan(check, project, files, runner, spec):
    scripts, header_findings = {}, {}
    for file in files:
        if Path(file).suffix in SHELL_EXTENSIONS:
            name, header_finding = script_shell(project / file)
            if header_finding:
                header_findings[file] = header_finding
            if name:
                scripts[file] = name

    tools = []
    for name in sorted(set(scripts.values())):
        path = local_shell(name) if runner.name == "local" else (name if runner.command_available(name) else None)
        if not path:
            raise ValueError(f"{name} is missing in the selected runner. On native Windows use Git for Windows.")
        tools.append(dict(name=name, path=path, source="runner"))
    return dict(tools=tools, environment={}, scripts=scripts, header_findings=header_findings)


def shell_run(lint):
    scripts = lint.selected["scripts"]
    header_findings = lint.selected["header_findings"]
    if not scripts and not header_findings:
        lint.na = "No changed sh or Bash scripts"
    for file, message in header_findings.items():
        lint.add(file, 1, message, source="shebang")
    for file, name in scripts.items():
        code, stdout, stderr = lint.call([lint.binary(name), "-n", "--", file], env={"BASH_ENV": None, "ENV": None})
        if code:
            message = (stderr or stdout).decode("utf-8", errors="replace").strip()
            match = SHELL_LINE.search(message)
            lint.add(file, match[1] if match else 0, message or f"{name} -n exited with status {code}", source=name)


SPEC = SimpleNamespace(
    id="generic",
    directory=Path(__file__).resolve().parent.parent,
    providers=(),
    core_configs=(),
    core_prefixes=(),
    code_extensions={".py", *SHELL_EXTENSIONS},
    excluded={".venv", "venv", "__pycache__", "node_modules", "vendor", "dist", "build"},
    runner=dict(name="local", services=("app",), root="/app"),
    extra_checks={
        "syntax": SimpleNamespace(applies=lambda paths: any(syntax_type(path) for path in paths), run=syntax_run),
        "shell": SimpleNamespace(applies=lambda paths: any(path.suffix in SHELL_EXTENSIONS for path in paths),
                                 run=shell_run, plan=shell_plan),
        "yaml": SimpleNamespace(applies=lambda paths: any(map(is_yaml, paths)), run=yaml_run, plan=yaml_plan),
    },
)
