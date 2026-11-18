import re
from pathlib import Path

from core_toolchain import config_evidence, node_config, versioned

YAML_SUFFIXES = {".yml", ".yaml"}
CONFIGS = (".yamllint", ".yamllint.yaml", ".yamllint.yml")
DIAGNOSTIC = re.compile(r"^.+?:(\d+):\d+: \[(error|warning)\] (.*)$")


def is_yaml(path):
    return path.suffix.lower() in YAML_SUFFIXES


def helm_template(project, path):
    return any(parent.name == "templates" and (parent.parent / "Chart.yaml").is_file()
               for parent in (project / path).parents if parent.is_relative_to(project))


def yaml_plan(check, project, files, runner, spec):
    selected = [path for path in files if is_yaml(Path(path)) and not helm_template(project, path)]
    if not selected:
        return dict(tools=[], environment={}, files=[])
    if not runner.command_available("yamllint"):
        raise ValueError("yamllint is unavailable in the selected runner")
    configs = {file: node_config(project, [file], CONFIGS) for file in selected}
    tool = versioned(runner, "yamllint", "yamllint", "runner")
    evidence = [config_evidence(project, config, "inline syntax-only")
                for config in sorted(set(configs.values()), key=lambda value: value or "")]
    return dict(tools=[tool], environment={}, files=selected, configs=configs, configurations=evidence)


def yaml_run(lint):
    files = lint.selected["files"]
    if not files:
        lint.na = "Changed YAML sources are Helm templates; use the project's renderer"
        return
    for file in files:
        config = lint.selected["configs"][file]
        options = ["-c", config] if config else ["-d", "{rules: {}}"]
        code, stdout, stderr = lint.call([lint.binary("yamllint"), "-f", "parsable", *options, "--", file])
        messages = [DIAGNOSTIC.fullmatch(line) for line in stdout.decode(errors="replace").splitlines() if line]
        if code not in {0, 1} or stderr.strip() or not all(messages) or code and not messages:
            lint.incomplete.append(f"yamllint did not produce a usable report for {file}; see log")
            continue
        for item in messages:
            line, severity, message = item.groups()
            lint.add(file, line, message, severity, "yamllint", filter_lines=not message.startswith("syntax error"))
