import os
import posixpath
import re
import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parent / "_shared/core"))
sys.path.insert(0, str(DIRECTORY.parents[1] / "scripts"))
from core_toolchain import config_evidence, managed_bundle, versioned
from dependency_support import asset_id

VENVS = (".venv", "venv")
INTERPRETED = {"syntax", "django", "migrations"}
BINARIES = {"ruff": "ruff", "format": "ruff", "bandit": "bandit", "audit": "pip-audit", "mypy": "mypy"}
MODULES = {"mypy": "mypy", "bandit": "bandit", "pip-audit": "pip_audit"}


def read(project, name):
    try:
        return (project / name).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def has_section(text, name):
    return bool(re.search(r"(?m)^\[" + re.escape(name) + r"[\].]", text))


def ruff_config(project):
    found = next((n for n in ("ruff.toml", ".ruff.toml") if (project / n).is_file()), None)
    return found or ("pyproject.toml" if has_section(read(project, "pyproject.toml"), "tool.ruff") else None)


def mypy_configured(project):
    return any((project / n).is_file() for n in ("mypy.ini", ".mypy.ini")) or \
        has_section(read(project, "pyproject.toml"), "tool.mypy") or bool(re.search(r"(?m)^\[mypy[\]-]", read(project, "setup.cfg")))


def bandit_configured(project):
    return has_section(read(project, "pyproject.toml"), "tool.bandit")


def django_project(project):
    return (project / "manage.py").is_file()


def bin_name(runner, name):
    windows = os.name == "nt" and runner.name == "local"
    return ("Scripts/" + name + ".exe") if windows else "bin/" + name


def resolve(runner, project):
    override = os.environ.get("READY_CHECK_PYTHON")

    if override:
        return [override], "env", override

    for folder in VENVS:
        path = runner.root + "/" + folder + "/" + bin_name(runner, "python")

        if runner.exists(path):
            return [path], "project", path

    if (project / "uv.lock").is_file() and runner.command_available("uv"):
        return ["uv", "run", "--no-sync", "python"], "uv", None

    if ((project / "poetry.lock").is_file() or has_section(read(project, "pyproject.toml"), "tool.poetry")) and runner.command_available("poetry"):
        return ["poetry", "run", "python"], "poetry", None
    name = next((n for n in ("python3", "python") if runner.command_available(n)), None)

    if not name:
        raise ValueError("Python is missing in the selected runner")

    return [name], "runner", None


def interpreter(runner, project):
    argv, source, plain = resolve(runner, project)
    status, stdout, stderr = runner.exec([*argv, "--version"], timeout=60)
    match = re.search(r"Python (\d+\.\d+\.\d+)", (stdout + stderr).decode(errors="replace"))

    if status or not match:
        raise ValueError(f"Cannot run the Python interpreter {' '.join(argv)}; existing interpreters are not replaced after failure")

    return argv, dict(name="python", path=" ".join(argv), source=source, version=match[1])


def executable(runner, project):
    argv, source, plain = resolve(runner, project)

    if plain:
        return plain
    status, stdout, _ = runner.exec([*argv, "-c", "import sys; print(sys.executable)"], timeout=60)
    path = stdout.decode(errors="replace").strip().splitlines()[-1:] if not status else []

    if not path:
        raise ValueError(f"Cannot locate the project interpreter through {' '.join(argv)} for mypy")

    return path[0]


def item(runner, folder, name, source, spec=None):
    if name not in MODULES:
        return versioned(runner, name, folder + "/" + bin_name(runner, name), source, spec=spec)
    python = folder + "/" + bin_name(runner, "python")
    status, stdout, stderr = runner.exec([python, "-m", MODULES[name], "--version"], timeout=120)
    match = re.search(r"(?<![\w.])v?(\d+\.\d+(?:\.\d+)?)", (stdout + stderr).decode(errors="replace"))

    if status or not match:
        raise ValueError(f"Cannot determine {name} version from {python}; existing tools are not replaced after failure")
    result = dict(name=name, path=python, module=MODULES[name], source=source, version=match[1])

    if source == "profile":
        result["bundle_id"] = asset_id(spec.bundle_source)

    return result


def tool(runner, project, name, spec):
    folders = [runner.root + "/" + folder for folder in VENVS]
    override = os.environ.get("READY_CHECK_PYTHON")

    if override:
        folders.insert(0, posixpath.dirname(posixpath.dirname(override.replace("\\", "/"))))

    for folder in folders:
        path = folder + "/" + bin_name(runner, name)

        if runner.exists(path):
            return item(runner, folder, name, "project")

    return item(runner, managed_bundle(runner, spec) + "/venv", name, "profile", spec)


def plan(check, project, files, runner, spec):
    tools, env = [], {}

    if check in {"django", "migrations"} and not django_project(project):
        return dict(tools=tools, environment=env)

    if check == "mypy" and not mypy_configured(project):
        return dict(tools=tools, environment=env)

    if check in BINARIES:
        selected = tool(runner, project, BINARIES[check], spec)
        tools.append(selected)

        if check in {"ruff", "format"}:
            config = ruff_config(project)

            if config:
                selected["configuration"] = config_evidence(project, config, None)
            else:
                env["LINT_RUFF_CONFIG"] = managed_bundle(runner, spec) + "/ruff.toml"
                selected["configuration"] = config_evidence(project, None, env["LINT_RUFF_CONFIG"])

        if check == "mypy" and selected["source"] == "profile":
            env["LINT_MYPY_PYTHON"] = executable(runner, project)

    if check in INTERPRETED:
        argv, version = interpreter(runner, project)
        env["LINT_PYTHON"] = argv
        tools.append(version)

    return dict(tools=tools, environment=env)
