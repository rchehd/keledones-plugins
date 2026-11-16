import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from dependency_support import PLUGIN, asset_files, asset_id, data_root
from process_support import execute


DDEV_DATA = "/mnt/ddev-global-cache/ready-check"
JS = {".js", ".mjs", ".cjs"}
STYLES = {".css", ".scss"}
ESLINT = ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", ".eslintrc.js",
          ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml", ".eslintrc")
STYLELINT = ("stylelint.config.js", "stylelint.config.mjs", "stylelint.config.cjs", ".stylelintrc",
             ".stylelintrc.json", ".stylelintrc.yml", ".stylelintrc.js")


def runner_data_root(runner, override=None):
    value = override or os.environ.get("READY_CHECK_RUNNER_DATA_DIR")

    if not value:
        if runner.name == "local":
            value = str(data_root())
        elif runner.name == "ddev" and runner.sh('[ -d "$1" ] && [ -w "$1" ] && echo 1 || echo 0',
                                                  str(PurePosixPath(DDEV_DATA).parent)).decode().strip() == "1":
            value = DDEV_DATA
        else:
            value = runner.sh('printf "%s" "${XDG_DATA_HOME:-$HOME/.local/share}/ready-check"').decode().strip()

    value = str(value)
    absolute = Path(value).is_absolute() if runner.name == "local" else PurePosixPath(value).is_absolute()

    if not absolute or any(character in value for character in ("\0", "\n", "\r")):
        raise ValueError("Runner data directory must be absolute and cannot contain NUL/newlines")

    return str(Path(value).resolve()) if runner.name == "local" else value


def bundle_digest(runner, directory, names):
    digest = hashlib.sha256()

    for name in names:
        digest.update(name.encode() + b"\0" + runner.read(directory + "/" + name))

    return digest.hexdigest()


def managed_bundle(runner, spec):
    if hasattr(runner, "managed_directory"):
        return runner.managed_directory

    path_type = Path if runner.name == "local" else PurePosixPath
    directory = str(path_type(runner_data_root(runner)) / spec.bundle_component / asset_id(spec.bundle_source)[:20])
    marker = directory + "/ready.json"

    if not runner.exists(marker):
        raise ValueError(f"Managed {spec.name} tools are not installed; invoke ready:setup or run Python " + str(PLUGIN / "scripts/ready-check.py")
                         + " setup"
                         + " --component profile --profile " + spec.id + " --project " + shlex.quote(str(runner.project)))

    spec.compatibility(runner)
    expected = asset_id(spec.bundle_source)

    try:
        metadata = json.loads(runner.read(marker))
        current = isinstance(metadata, dict) and metadata.get("asset_id") == expected and bundle_digest(
            runner, directory, [p.name for p in asset_files(spec.bundle_source)]) == expected
    except (OSError, ValueError):
        current = False

    if not current:
        raise ValueError("Managed tool manifests/configuration changed; repeat the separate profile setup")

    runner.managed_directory = directory
    return directory


def versioned(runner, name, path, source, config=None, spec=None):
    status, stdout, stderr = runner.exec([path, "--version"], timeout=30)
    output = (stdout + stderr).decode(errors="replace")
    match = re.search(r"(?<![\w.])v?(\d+\.\d+(?:\.\d+)?(?:-[\w.-]+)?)", output)

    if status or not match:
        raise ValueError(f"Cannot determine {name} version from {path}; existing tools are not replaced after failure")
    item = dict(name=name, path=path, source=source, version=match[1])

    if source == "profile":
        item["bundle_id"] = asset_id(spec.bundle_source)

    if config:
        item["configuration"] = config
    return item


def config_evidence(project, path, default):
    if path:
        file = project / path
        return dict(source="project", path=path, sha256=hashlib.sha256(file.read_bytes()).hexdigest())
    return dict(source="profile", path=default)


def usable_config(project, config, core, ignored):
    relative = config.relative_to(project).as_posix()

    if relative.startswith(core):
        return False

    if config.suffix == ".json" or config.name in {".eslintrc", ".stylelintrc"}:
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, ValueError, AttributeError):
            return True

        if not isinstance(data, dict) or set(data) != {"extends"}:
            return True
        extends = data["extends"]
        extends = [extends] if isinstance(extends, str) else extends
        targets = {(project / prefix / name).resolve() for prefix in core for name in ignored}

        if isinstance(extends, list) and extends and all(
                isinstance(entry, str) and (config.parent / entry).resolve() in targets for entry in extends):
            return False
    return True


def node_config(project, files, names, core=(), ignored=()):
    found = set()

    for name in files:
        parent = (project / name).parent

        while parent.is_relative_to(project):
            config = next((p for p in (parent / n for n in names) if p.is_file() and usable_config(project, p, core, ignored)), None)

            if config:
                found.add(config.relative_to(project).as_posix())
                break

            if parent == project:
                break
            parent = parent.parent

    if not found:
        return None

    if len(found) != 1:
        raise ValueError("A single applicable project linter configuration is required")
    return next(iter(found))




def node_config(project, files, names, core=(), ignored=()):
    found = set()

    for name in files:
        parent = (project / name).parent

        while parent.is_relative_to(project):
            config = next((p for p in (parent / n for n in names) if p.is_file() and usable_config(project, p, core, ignored)), None)

            if config:
                found.add(config.relative_to(project).as_posix())
                break

            if parent == project:
                break
            parent = parent.parent

    if not found:
        return None

    if len(found) != 1:
        raise ValueError("A single applicable project linter configuration is required")
    return next(iter(found))


def node_runtime(runner, tools):
    item = versioned(runner, "node", "node", "runner")
    managed_js = any(t.get("source") == "profile" or t.get("configuration", {}).get("source") == "profile"
                     for t in tools if t["name"] in {"eslint", "stylelint", "jscpd"})

    if managed_js and int(item["version"].split(".")[0]) < 20:
        raise ValueError("Managed JavaScript tools/defaults require runner Node.js 20 or newer")

    return item


def select(check, project, files, runner, node_config, spec):
    tools, env = [], {}

    if check == "js":
        for extensions, binary, names in ((JS, "eslint", ESLINT), (STYLES, "stylelint", STYLELINT)):
            selected = [p for p in files if Path(p).suffix in extensions]

            if not selected:
                continue
            config = node_config(project, selected, names)
            candidates = [(Path(config).parent / "node_modules/.bin" / binary).as_posix()] if config else ["node_modules/.bin/" + binary]
            candidates = [runner.root + "/" + path for path in candidates]
            executable = next((p for p in candidates if runner.exists(p)), None)
            source = "project" if executable else "profile"
            bundle = managed_bundle(runner, spec) if not executable or not config else None
            executable = executable or bundle + "/node_modules/.bin/" + binary
            item = versioned(runner, binary, executable, source, spec=spec)

            if not config and binary == "eslint" and int(item["version"].split(".")[0]) != 9:
                raise ValueError("Profile ESLint defaults require ESLint 9; existing incompatible tools are not replaced")
            default = "eslint.config.mjs" if binary == "eslint" else "stylelint.config.json"
            config_path = runner.root + "/" + config if config else bundle + "/" + default
            item["configuration"] = config_evidence(project, config, config_path)
            prefix = "LINT_" + binary.upper()
            env[prefix + "_BIN"], env[prefix + "_CONFIG"] = executable, config_path

            if binary == "eslint" and config and Path(config).name.startswith(".eslintrc"):
                if int(item["version"].split(".")[0]) > 9:
                    raise ValueError("Legacy ESLint configuration requires a compatible existing executable")
                env["LINT_ESLINT_LEGACY"] = "1"
            tools.append(item)

    if check == "dup":
        project_path = runner.root + "/node_modules/.bin/jscpd"
        path = os.environ.get("LINT_JSCPD") or shutil.which("jscpd")

        if runner.exists(project_path):
            path = project_path
            tools.append(versioned(runner, "jscpd", path, "project"))
            env["LINT_JSCPD_RUNNER"] = "1"
        elif path:
            try:
                code, stdout, stderr = execute([path, "--version"], project, timeout=15)
            except (subprocess.TimeoutExpired, ValueError):
                raise ValueError("Existing host jscpd version probe timed out")
            match = re.search(r"\b(\d+\.\d+\.\d+)", (stdout + stderr).decode(errors="replace"))

            if code or not match:
                raise ValueError("Existing host jscpd is unavailable")
            tools.append(dict(name="jscpd", path=path, source="shared", version=match[1]))
        else:
            path = managed_bundle(runner, spec) + "/node_modules/.bin/jscpd"
            tools.append(versioned(runner, "jscpd", path, "profile", spec=spec))
            env["LINT_JSCPD_RUNNER"] = "1"
        env["LINT_JSCPD"] = path

    if check == "js" or env.get("LINT_JSCPD_RUNNER") == "1":
        tools.append(node_runtime(runner, tools))

    return dict(tools=tools, environment=env)
