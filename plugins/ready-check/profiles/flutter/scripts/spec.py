import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parents[1] / "scripts"))
from process_support import find_command
from project import toplevel

ANALYSIS_INPUTS = {"pubspec.yaml", "pubspec.lock", "pubspec_overrides.yaml", "analysis_options.yaml", ".fvmrc"}
ANALYZER_LINE = re.compile(
    r"^\s*(?:error|warning|info)\s+(?P<sep>[-•])\s+(?P<message>.+)\s+(?P=sep)\s+"
    r"(?P<file>.+):(?P<line>\d+):\d+\s+(?P=sep)\s+(?P<rule>\S*)\s*$"
)


def dart_source(path):
    return path.suffix == ".dart"


def analysis_input(path):
    return dart_source(path) or path.name in ANALYSIS_INPUTS


def workspace_roots(project, runner):
    top = (toplevel(project) or project) if runner.name == "local" else project
    return [directory for directory in (project, *project.parents) if directory.is_relative_to(top)]


def sdk_launcher(project, runner, windows):
    filename = "flutter.bat" if windows else "flutter"
    for directory in workspace_roots(project, runner):
        root = str(directory) if runner.name == "local" else runner.root
        path = root + "/.fvm/flutter_sdk/bin/" + filename
        if runner.exists(path):
            return path, "project"
        if any(runner.exists(root + "/" + name) for name in (".fvmrc", ".fvm/fvm_config.json")):
            raise ValueError("The project pins Flutter with FVM. Prepare its SDK before running checks.")
    if runner.name == "local":
        installed = os.environ.get("FLUTTER_ROOT")
        if installed:
            return str(Path(installed) / "bin" / filename), "runner"
        if path := find_command("flutter"):
            return path, "runner"
    elif runner.command_available("flutter"):
        return runner.sh('command -v flutter').decode("utf-8").strip(), "runner"
    raise ValueError("Flutter SDK is unavailable in the selected runner")


def sdk_plan(project, runner):
    if "flutter" in runner.cache:
        return runner.cache["flutter"]
    windows = runner.name == "local" and os.name == "nt"
    path_type = Path if runner.name == "local" else PurePosixPath
    launcher, source = sdk_launcher(project, runner, windows)
    flutter = path_type(runner.realpath(launcher))
    sdk = flutter.parent.parent
    snapshot = sdk / "bin/cache/flutter_tools.snapshot"
    dart = sdk / ("bin/cache/dart-sdk/bin/dart.exe" if windows else "bin/cache/dart-sdk/bin/dart")
    if not all(runner.exists(str(path)) for path in (flutter, snapshot, dart)):
        raise ValueError("Flutter SDK cache is incomplete. Prepare the project's Flutter installation.")

    if windows:
        packages = sdk / "packages/flutter_tools/.dart_tool/package_config.json"
        if not runner.exists(str(packages)):
            raise ValueError("Flutter tool package configuration is missing. Prepare the Flutter SDK.")
        command = [str(dart), f"--packages={packages}", str(snapshot)]
    else:
        command = [str(flutter)]
    environment = {"FLUTTER_ROOT": str(sdk)}
    command.append("--suppress-analytics")
    code, stdout, _ = runner.exec([*command, "--version", "--machine"], timeout=30, env=environment)
    if code:
        raise ValueError("Could not read the Flutter SDK version. Check the selected installation.")
    details = json.loads(stdout)
    flutter_version = details.get("frameworkVersion") if isinstance(details, dict) else None
    dart_version = details.get("dartSdkVersion") if isinstance(details, dict) else None
    if not all(isinstance(version, str) and version.strip() for version in (flutter_version, dart_version)):
        raise ValueError("Flutter did not report its Flutter and Dart SDK versions")
    tools = [dict(name="flutter", version=flutter_version, path=str(flutter), source=source),
             dict(name="dart", version=dart_version, path=str(dart), source="flutter-sdk")]
    result = dict(tools=tools, environment=environment, flutter=command, dart=str(dart))
    runner.cache["flutter"] = result
    return result


def package_config(project, runner):
    for directory in workspace_roots(project, runner):
        root = str(directory) if runner.name == "local" else runner.root
        path = root + "/.dart_tool/package_config.json"
        if runner.exists(path):
            return dict(path=path, sha256=hashlib.sha256(runner.read(path)).hexdigest())
    raise ValueError("Flutter project packages are unavailable. Prepare dependencies with the project's SDK.")


def analyze_plan(check, project, files, runner, spec):
    dependencies = package_config(project, runner)
    return dict(sdk_plan(project, runner), packages=dependencies)


def format_plan(check, project, files, runner, spec):
    return dict(sdk_plan(project, runner), files=[file for file in files if dart_source(Path(file))])


def analyze_run(lint):
    code, stdout, stderr = lint.call([*lint.selected["flutter"], "--no-color", "--no-wrap", "analyze", "--no-pub"],
                                     env=lint.selected["environment"])
    found = False
    for line in (stdout + b"\n" + stderr).decode("utf-8", errors="replace").splitlines():
        match = ANALYZER_LINE.fullmatch(line)
        if match:
            lint.add(match["file"], match["line"], match["message"], "error" if code else "warning",
                     match["rule"] or "flutter-analyze")
            found = True
    if code and (code != 1 or not found):
        lint.incomplete.append("Flutter analysis did not complete with usable diagnostics. See log.")


def format_run(lint):
    for file in lint.selected["files"]:
        code, stdout, _ = lint.call([lint.selected["dart"], "format", "--output=none", "--set-exit-if-changed",
                                     lint.runner.path(file)], env=lint.selected["environment"])
        if code == 1 and any(line.startswith(b"Changed ") for line in stdout.splitlines()):
            lint.add(file, 0, "Dart formatter would change this file", source="dart-format")
        elif code:
            lint.incomplete.append(f"Dart formatting check could not finish for {file}. See log.")


SPEC = SimpleNamespace(
    id="flutter", name="Flutter", directory=DIRECTORY,
    providers=(), core_configs=(), core_prefixes=(), code_extensions={".dart"},
    excluded={".dart_tool", ".fvm", "build", "coverage", "node_modules", "vendor"},
    runner=dict(name="local", services=("flutter", "app"), root="/app"),
    extra_checks={
        "flutter-analyze": SimpleNamespace(applies=lambda paths: any(map(analysis_input, paths)),
                                            plan=analyze_plan, run=analyze_run),
        "dart-format": SimpleNamespace(applies=lambda paths: any(map(dart_source, paths)),
                                       plan=format_plan, run=format_run),
    },
)
