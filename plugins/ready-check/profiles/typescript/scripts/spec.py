import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parents[1] / "scripts"))
sys.path.insert(0, str(DIRECTORY.parent / "_shared/core"))
from core_toolchain import ESLINT, config_evidence, managed_bundle, versioned
from project import toplevel

EXTENSIONS = {".ts", ".tsx", ".mts", ".cts"}
CONFIGS = (*ESLINT, "eslint.config.ts", "eslint.config.mts", "eslint.config.cts", ".eslintrc.cjs")
PACKAGE_FILES = {"package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock"}
ENTRIES = {"typescript": "typescript/bin/tsc", "eslint": "eslint/bin/eslint.js"}
HELPER = DIRECTORY / "tools/typecheck.cjs"


def ts_source(path):
    return path.suffix in EXTENSIONS


def ts_config(path):
    return path.name == "tsconfig.json" or path.match("tsconfig.*.json")


def ts_input(path):
    return ts_source(path) or ts_config(path) or path.name in PACKAGE_FILES


def ancestors(directory, root):
    return (path for path in (directory, *directory.parents) if path.is_relative_to(root))


def configs_for(project, file):
    path = project / file
    if ts_config(path):
        return [path]
    for directory in ancestors(path.parent, project):
        canonical = directory / "tsconfig.json"
        if canonical.is_file():
            return [canonical]
        named = sorted(directory.glob("tsconfig.*.json"))
        if named:
            return named
    raise ValueError(f"No TypeScript project configuration covers {file}")


def tool_for(project, runner, spec, package, directory, repo):
    entry = ENTRIES[package]
    for parent in ancestors(directory, repo):
        node_modules = parent / "node_modules"
        prefix = str(node_modules) if runner.name == "local" else runner.path(node_modules.relative_to(project).as_posix())
        path = prefix + "/" + entry
        if runner.exists(path):
            return versioned(runner, package, path, "project", spec=spec), prefix
    prefix = managed_bundle(runner, spec) + "/node_modules"
    if not runner.exists(prefix + "/" + entry):
        raise ValueError(f"Managed {package} is missing; run profile setup again")
    return versioned(runner, package, prefix + "/" + entry, "profile", spec=spec), prefix


def typecheck_plan(check, project, files, runner, spec):
    repo = (toplevel(project) or project) if runner.name == "local" else project
    groups = {}
    for file in files:
        if ts_input(Path(file)):
            for config in configs_for(project, file):
                groups.setdefault(config, []).append(file)
    tools = [versioned(runner, "node", "node", "runner")]
    targets = []
    for config, inputs in groups.items():
        relative = config.relative_to(project).as_posix()
        if not config.resolve().is_relative_to(project):
            raise ValueError(f"TypeScript config must be inside the application: {relative}")
        tool, prefix = tool_for(project, runner, spec, "typescript", config.parent, repo)
        tools.append(tool)
        targets.append(dict(config=relative, inputs=inputs, compiler=prefix + "/typescript/lib/typescript.js",
                            configuration=config_evidence(project, relative, None)))
    return dict(tools=tools, environment={}, targets=targets, helper=hashlib.sha256(HELPER.read_bytes()).hexdigest())


def typecheck_run(lint):
    helper = lint.temporary("typecheck.cjs", HELPER.read_text(encoding="utf-8"))
    expected, compiled = set(), set()
    for target in lint.selected["targets"]:
        config = lint.runner.path(target["config"])
        expected.update(file for file in target["inputs"] if ts_source(Path(file)))
        code, out, err = lint.call(["node", helper, target["compiler"], config])
        if code:
            lint.incomplete.append(f"TypeScript compiler failed to run for {target['config']}; see log")
            continue
        result = json.loads(out)
        compiled.update(lint.relative(file) for file in result["files"])
        if result["status"] and not result["diagnostics"]:
            lint.incomplete.append(f"TypeScript returned no diagnostic for {target['config']}; see log")
        for item in result["diagnostics"]:
            lint.add(item["file"], item["line"], item["message"], source=f"TS{item['code']}")
    if not lint.findings:
        for file in sorted(expected - compiled):
            lint.incomplete.append(f"Changed file is outside the configured TypeScript programs: {file}")


def eslint_plan(check, project, files, runner, spec):
    repo = (toplevel(project) or project) if runner.name == "local" else project
    groups = {}
    for file in files:
        if ts_source(Path(file)):
            directory = (project / file).parent
            config = next((folder / name for folder in ancestors(directory, repo)
                           for name in CONFIGS if (folder / name).is_file()), None)
            root = config.parent if config else configs_for(project, file)[0].parent
            groups.setdefault((root, config), []).append(file)
    tools = [versioned(runner, "node", "node", "runner")]
    targets = []
    for (root, config), inputs in groups.items():
        tool, _ = tool_for(project, runner, spec, "eslint", root, repo)
        tools.append(tool)
        cwd = str(root) if runner.name == "local" else runner.path(root.relative_to(project).as_posix())
        if config:
            config_path = str(config) if runner.name == "local" else runner.path(config.relative_to(project).as_posix())
        else:
            if not tool["version"].startswith("9."):
                raise ValueError("Managed TypeScript ESLint config requires ESLint 9 or a project config")
            config_path = managed_bundle(runner, spec) + "/eslint.config.mjs"
        evidence = config_evidence(repo, config.relative_to(repo).as_posix() if config else None, config_path)
        legacy = bool(config and config.name.startswith(".eslintrc"))
        targets.append(dict(cwd=cwd, config=config_path, files=[runner.path(file) for file in inputs],
                            executable=tool["path"], configuration=evidence, legacy=legacy))
    return dict(tools=tools, environment={}, targets=targets)


def eslint_run(lint):
    for target in lint.selected["targets"]:
        status, stdout, stderr = lint.call([target["executable"], "--no-cache", "--format", "json",
                                            "--config", target["config"], "--", *target["files"]],
                                           env={"ESLINT_USE_FLAT_CONFIG": "false" if target["legacy"] else "true"},
                                           cwd=target["cwd"])
        lint.parse("eslint", status, stdout, stderr)


SPEC = SimpleNamespace(
    id="typescript", name="TypeScript", directory=DIRECTORY,
    providers=(), core_configs=(), core_prefixes=(), code_extensions=EXTENSIONS,
    excluded={"node_modules", "vendor", "dist", "build", "coverage"},
    runner=dict(services=("node", "frontend", "app"), root="/app"),
    bundle_source=DIRECTORY / "tools", bundle_component="profiles/typescript",
    bundle_binaries=dict(node=("eslint",)), compatibility=lambda runner: {},
    extra_checks={
        "typecheck": SimpleNamespace(applies=lambda paths: any(map(ts_input, paths)), plan=typecheck_plan, run=typecheck_run),
        "eslint": SimpleNamespace(applies=lambda paths: any(map(ts_source, paths)), plan=eslint_plan, run=eslint_run),
    },
)
