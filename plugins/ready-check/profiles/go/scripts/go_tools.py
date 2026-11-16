import json
import os
import posixpath
import re
import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parent / "_shared/core"))
from core_toolchain import config_evidence, managed_bundle, versioned

GOLANGCI_CONFIGS = (".golangci.yml", ".golangci.yaml", ".golangci.toml", ".golangci.json")
GO_VERSION = re.compile(r"go(\d+\.\d+(?:\.\d+)?)")
MANAGED = {"golangci": "golangci-lint", "govulncheck": "govulncheck"}


def manifest():
    return json.loads((DIRECTORY / "tools/tools.json").read_text(encoding="utf-8"))


def executable(runner, name):
    return name + ".exe" if os.name == "nt" and runner.name == "local" else name


def golangci_config(project):
    return next((n for n in GOLANGCI_CONFIGS if (project / n).is_file()), None)


def go_version(runner):
    status, stdout, stderr = runner.exec(["go", "version"], timeout=60)
    match = GO_VERSION.search((stdout + stderr).decode(errors="replace"))

    if status or not match:
        raise ValueError("Cannot run go in the selected runner; existing toolchains are not replaced after failure")

    return dict(name="go", path="go", source="runner", version=match[1])


def go_env(runner, name):
    status, stdout, _ = runner.exec(["go", "env", name], timeout=60)

    return stdout.decode(errors="replace").strip() if not status else ""


def gofmt_item(runner, go):
    root = go_env(runner, "GOROOT")
    path = posixpath.join(root.replace("\\", "/"), "bin", executable(runner, "gofmt")) if root else ""

    if not path or not runner.exists(path):
        path = "gofmt"

        if not runner.command_available(path):
            raise ValueError("gofmt is missing next to the project's go and on PATH")

    return dict(name="gofmt", path=path, source="runner", version=go["version"])


def project_tool(runner, name):
    if runner.command_available(name):
        return name
    folders = [go_env(runner, "GOBIN")] + [posixpath.join(p.replace("\\", "/"), "bin") for p in go_env(runner, "GOPATH").split(os.pathsep) if p]

    for folder in folders:
        path = posixpath.join(folder.replace("\\", "/"), executable(runner, name)) if folder else ""

        if path and runner.exists(path):
            return path

    return None


def tool(runner, name, spec, minimum_major=0):
    path = project_tool(runner, name)

    if path:
        found = versioned(runner, name, path, "project")

        if int(found["version"].split(".")[0]) >= minimum_major:
            return found

    return versioned(runner, name, managed_bundle(runner, spec) + "/bin/" + executable(runner, name), "profile", spec=spec)


def plan(check, project, files, runner, spec):
    if not runner.command_available("go"):
        raise ValueError("Go is missing in the selected runner")
    go = go_version(runner)
    tools, env = [gofmt_item(runner, go) if check == "gofmt" else go], {}

    if check in MANAGED:
        config = golangci_config(project) if check == "golangci" else None
        # The managed default config is v2, so a v1 binary is used only with the project's own config.
        selected = tool(runner, MANAGED[check], spec, 2 if check == "golangci" and not config else 0)
        tools.append(selected)

        if check == "golangci":
            if config:
                env["LINT_GOLANGCI_CONFIG"] = runner.root + "/" + config
                selected["configuration"] = config_evidence(project, config, None)
            else:
                env["LINT_GOLANGCI_CONFIG"] = managed_bundle(runner, spec) + "/golangci.yml"
                selected["configuration"] = config_evidence(project, None, env["LINT_GOLANGCI_CONFIG"])

    return dict(tools=tools, environment=env)
