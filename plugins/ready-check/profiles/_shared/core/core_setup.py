import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core_runner import Runner
from core_toolchain import runner_data_root, versioned
from dependency_support import PLUGIN, asset_files, asset_id, outside_repositories, release_lock, take_lock
from managed_storage import prepare_storage
from settings import project_config


def file_digest(runner, path):
    try:
        return hashlib.sha256(runner.read(path)).hexdigest()
    except OSError:
        return "missing"


def setup(project, host_root, override, dry_run, timeout, spec, ecosystems=()):
    source = spec.bundle_source
    runner = Runner(project, project_config(project), spec.runner)
    root = runner_data_root(runner, override or os.environ.get("READY_CHECK_RUNNER_DATA_DIR")
                            or (str(host_root) if runner.name == "local" else None))
    path_type = Path if runner.name == "local" else PurePosixPath
    destination = str(path_type(root) / spec.bundle_component / asset_id(source)[:20])
    details = dict(component=spec.id, host_platform=sys.platform, runner=runner.name, directory=destination, bundle_id=asset_id(source))

    if dry_run:
        if runner.name == "local":
            prepare_storage(root, destination, source, spec.bundle_component, dry_run=True)

        return dict(status="PLANNED", **details)

    if not runner.available():
        raise ValueError(f"Selected {runner.name} runner is unavailable")

    details.update(spec.compatibility(runner))
    prepare_storage(root, destination, source, spec.bundle_component, runner, dry_run=True)
    destination = runner.realpath(destination)
    root = runner.realpath(root)

    if runner.name == "local":
        outside_repositories(Path(destination), project)

    forbidden = [runner.realpath(runner.root), str(PLUGIN)]
    code, stdout, _ = runner.exec(["git", "rev-parse", "--show-toplevel"])

    if not code:
        forbidden.append(stdout.decode().strip())

    if any(destination == path or destination.startswith(path.rstrip("/") + "/") for path in forbidden):
        raise ValueError("Runner dependencies must be outside the project repository and plugin package")

    for binary in (*(b for ecosystem in ecosystems for b in ecosystem.binaries), "node", "npm"):
        if not runner.command_available(binary):
            raise ValueError(f"Profile setup requires existing {binary} in runner {runner.name}")

    node = versioned(runner, "node", "node", "runner")["version"]

    if int(node.split(".")[0]) < 20:
        raise ValueError(f"Managed {spec.name} JavaScript tools require runner Node.js 20 or newer")

    prepare_storage(root, destination, source, spec.bundle_component, runner)
    lock = destination + "/.setup-lock"
    take_lock(lock, timeout, runner)
    log = destination + "/setup.log"

    def call(argv, env=None):
        status, stdout, stderr = runner.exec(argv, timeout=timeout, cwd=destination, env=env)
        runner.write(log, stdout + stderr + b"\n", append=True)

        if status:
            raise ValueError(f"Profile setup command failed ({status}); see runner log {log}")

        return stdout.decode(errors="replace").strip()

    context = SimpleNamespace(runner=runner, spec=spec, root=root, destination=destination, path_type=path_type, call=call)

    try:
        marker = destination + "/ready.json"
        existing = runner.read(marker) if runner.exists(marker) else b""

        try:
            metadata = json.loads(existing)
            reuse = isinstance(metadata, dict) and metadata.get("asset_id") == asset_id(source)
        except ValueError:
            reuse = False

        for file in asset_files(source):
            if reuse and file_digest(runner, destination + "/" + file.name) != hashlib.sha256(file.read_bytes()).hexdigest():
                reuse = False

        for ecosystem in ecosystems:
            if not ecosystem.ready(context):
                reuse = False

        for binary in spec.bundle_binaries.get("node", ()):
            if not runner.exists(destination + "/node_modules/.bin/" + binary):
                reuse = False

        runner.unlink(marker)

        for file in asset_files(source):
            runner.write(destination + "/" + file.name, file.read_bytes())

        if not reuse:
            for ecosystem in ecosystems:
                ecosystem.install(context)

            node_env = dict.fromkeys(("npm_config_prefix", "NPM_CONFIG_PREFIX", "NODE_OPTIONS", "NODE_PATH"))
            node_env.update(npm_config_cache=str(path_type(root) / "npm-cache"), npm_config_engine_strict="true")
            call(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], node_env)

        tools = []

        for ecosystem in ecosystems:
            ecosystem.finalize(context)
            tools += ecosystem.tools(context)

        tools += [versioned(runner, name, destination + "/node_modules/.bin/" + name, "profile", spec=spec)
                  for name in spec.bundle_binaries.get("node", ())]
        details.update(directory=destination, node=node, reused=reuse, tools=tools)
        runner.write(destination + "/ready.tmp", (json.dumps(dict(asset_id=asset_id(source), **details), indent=2) + "\n").encode())
        runner.replace(destination + "/ready.tmp", marker)

        return dict(status="PASS", **details)
    finally:
        release_lock(lock, runner)
