import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parents[1] / "scripts"))
sys.path.insert(0, str(DIRECTORY.parent / "_shared/core"))
from core_toolchain import config_evidence
from settings import shared_config, valid
from yaml_checks import is_yaml, yaml_plan, yaml_run

COMPOSE_BASE = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
COMPOSE_OVERRIDE = ("compose.override.yaml", "compose.override.yml", "docker-compose.override.yaml", "docker-compose.override.yml")
VERSION = re.compile(rb"\bv?(\d+\.\d+(?:\.\d+)?(?:-[\w.-]+)?)")


def actionlint_file(path):
    return is_yaml(path) and path.parent.as_posix() == ".github/workflows"


def compose_file(path):
    return is_yaml(path) and path.parent == Path(".") and path.name.startswith(("compose.", "docker-compose."))


def ddev_file(path):
    return path.parent == Path(".ddev") and is_yaml(path) and path.name.startswith("config.")


def ddev_compose_file(path):
    return path.parent == Path(".ddev") and is_yaml(path) and path.name.startswith("docker-compose.")


def nginx_file(path):
    return path.name == "nginx.conf" or path.suffix == ".conf" and path.parts[0] == "nginx"


def gitlab_file(path):
    return is_yaml(path) and (path.as_posix() in {".gitlab-ci.yml", ".gitlab-ci.yaml"} or path.parts[:2] == (".gitlab", "ci"))


def probe(runner, name, command):
    if not runner.command_available(command[0]):
        raise ValueError(f"{name} is unavailable in the selected runner")
    status, out, err = runner.exec(command)
    version = VERSION.search(out + err)
    if status or not version:
        raise ValueError(f"Could not determine {name} version in the selected runner")
    return dict(name=name, version=version[1].decode(), path=command[0], source="runner")


def options(project):
    result = shared_config(project).get("devops", {})
    if not isinstance(result, dict):
        raise ValueError("The devops settings must be a JSON object")
    return result


def local_path(project, relative, directory=False):
    if not valid("application", relative):
        raise ValueError(f"Invalid DevOps path: {relative!r}")
    path = (project / relative).resolve()
    if not path.is_relative_to(project) or not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"DevOps path must exist within the application: {relative}")
    return path.relative_to(project).as_posix()


def commands(tool, paths, *argv, **context):
    return dict(tools=[tool], environment={}, paths=paths, commands=list(argv), **context)


def actionlint_plan(check, project, files, runner, spec):
    paths = [file for file in files if actionlint_file(Path(file))]
    tool = probe(runner, "actionlint", ["actionlint", "-version"])
    return commands(tool, paths, ["actionlint", "-format", "{{json .}}", *paths])


def actionlint_run(lint):
    status, output, _ = lint.call(lint.selected["commands"][0])
    if not output.strip() and not status:
        return
    items = json.loads(output)
    if not isinstance(items, list) or status not in {0, 1} or (status and not items):
        raise ValueError("actionlint did not produce a usable report")
    for item in items:
        lint.add(item["filepath"], item["line"], item["message"], source=item["kind"], filter_lines=item["kind"] != "syntax-check")


def compose_plan(check, project, files, runner, spec):
    paths = [file for file in files if compose_file(Path(file))]
    configured = options(project).get("compose_files")
    if configured is None and runner.name == "local" and os.environ.get("COMPOSE_FILE"):
        variable = os.environ.get("COMPOSE_PATH_SEPARATOR") or os.pathsep
        configured = [os.path.relpath(project / value, project).replace(os.sep, "/")
                      for value in os.environ["COMPOSE_FILE"].split(variable)]
    if configured is None:
        base = next((name for name in COMPOSE_BASE if (project / name).is_file()), None)
        override = next((name for name in COMPOSE_OVERRIDE if (project / name).is_file()), None)
        configured = [name for name in (base, override) if name]
    if not isinstance(configured, list) or not configured:
        raise ValueError("Set devops.compose_files to the intended ordered Compose files in .ready-check.json")
    selected = [local_path(project, path) for path in configured]
    if not set(paths) <= set(selected):
        raise ValueError("Changed Compose file is outside the selected stack; set devops.compose_files")
    tool = probe(runner, "Docker Compose", ["docker", "compose", "version"])
    argv = ["docker", "compose", *(arg for path in selected for arg in ("-f", path)), "config", "--quiet"]
    return commands(tool, paths, argv, configurations=[config_evidence(project, path, None) for path in selected])


def ddev_plan(check, project, files, runner, spec):
    paths = [file for file in files if ddev_file(Path(file))]
    if not (project / ".ddev/config.yaml").is_file():
        raise ValueError("DDEV project configuration is missing")
    tool = probe(runner, "DDEV", ["ddev", "--version"])
    return commands(tool, paths, ["ddev", "utility", "configyaml", "--full-yaml"])


def nginx_plan(check, project, files, runner, spec):
    paths = [file for file in files if nginx_file(Path(file))]
    config = options(project)
    filename = local_path(project, config.get("nginx_config", "nginx.conf"))
    prefix = local_path(project, config.get("nginx_prefix", "."), directory=True)
    tool = probe(runner, "Nginx", ["nginx", "-v"])
    argv = ["nginx", "-t", "-q", "-e", "stderr", "-c", runner.path(filename), "-p", runner.path(prefix)]
    return commands(tool, paths, argv, configurations=[config_evidence(project, filename, None)])


def quiet_run(lint):
    for argv in lint.selected["commands"]:
        status, out, err = lint.runner.exec(argv, lint.timeout)
        with lint.log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(argv) + f" exited with status {status}\n")
        output = (out + err).lower()
        if lint.check == "compose" and any(message in output for message in
                                           (b"variable is not set", b"required variable", b"env file")):
            lint.incomplete.append("Compose interpolation inputs are missing from the selected environment")
        elif status and lint.check == "compose":
            lint.add(lint.selected["paths"][0], 0, "Compose rejected the selected stack. Inspect local command output.")
        elif status and lint.check == "nginx" and any(message in output for message in
                                                      (b"unexpected ", b"invalid number of arguments", b"unknown directive")):
            lint.add(lint.selected["paths"][0], 0, "Nginx rejected a configuration directive. Inspect local command output.")
        elif status or (lint.check == "ddev" and not out.strip()):
            lint.incomplete.append(f"{argv[0]} could not validate the configuration in this environment. Inspect local command output.")


def gitlab_plan(check, project, files, runner, spec):
    return yaml_plan(check, project, [file for file in files if gitlab_file(Path(file))], runner, spec)


def ddev_compose_plan(check, project, files, runner, spec):
    return yaml_plan(check, project, [file for file in files if ddev_compose_file(Path(file))], runner, spec)


SPEC = SimpleNamespace(
    id="devops", name="DevOps", directory=DIRECTORY,
    providers=(), core_configs=(), core_prefixes=(), code_extensions=set(),
    excluded={"node_modules", "vendor", "dist", "build"},
    runner=dict(name="local", services=("app", "nginx"), root="/app"),
    extra_checks={
        "actionlint": SimpleNamespace(applies=lambda paths: any(map(actionlint_file, paths)), plan=actionlint_plan, run=actionlint_run),
        "compose": SimpleNamespace(applies=lambda paths: any(map(compose_file, paths)), plan=compose_plan, run=quiet_run),
        "ddev": SimpleNamespace(applies=lambda paths: any(map(ddev_file, paths)), plan=ddev_plan, run=quiet_run),
        "ddev-compose-yaml": SimpleNamespace(applies=lambda paths: any(map(ddev_compose_file, paths)), plan=ddev_compose_plan, run=yaml_run),
        "nginx": SimpleNamespace(applies=lambda paths: any(map(nginx_file, paths)), plan=nginx_plan, run=quiet_run),
        "gitlab-yaml": SimpleNamespace(applies=lambda paths: any(map(gitlab_file, paths)), plan=gitlab_plan, run=yaml_run),
    },
)
