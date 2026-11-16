import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core_toolchain import config_evidence, managed_bundle, versioned
from php_runtime import is_php, php


def composer_tool(runner, binary, spec):
    candidates = [(runner.root, "project")]

    if runner.tools:
        candidates.append((runner.tools, "shared"))

    for root, source in candidates:
        path = root + "/vendor/bin/" + binary

        if runner.exists(path):
            return versioned(runner, binary, path, source), root
    root = managed_bundle(runner, spec)
    path = root + "/vendor/bin/" + binary
    return versioned(runner, binary, path, "profile", spec=spec), root


PHP_CHECKS = {"phpcs", "phpstan", "syntax", "phpmd", "deadcode", "composer", "audit"}


def needs_php(check, spec):
    return check in PHP_CHECKS or check in spec.extra_checks and spec.extra_checks[check].php


def tool_binaries(spec):
    binaries = {"phpcs": "phpcs", "phpstan": "phpstan", "phpmd": "phpmd", "deadcode": "phpstan"}
    binaries.update({name: extra.tool for name, extra in spec.extra_checks.items() if extra.tool})
    return binaries


def selection(check, project, files, runner, spec):
    tools, env = [], {}
    binaries = tool_binaries(spec)

    if check in binaries:
        item, root = composer_tool(runner, binaries[check], spec)
        tools.append(item)

        if check == "phpcs":
            env["LINT_PHPCS_BIN"] = item["path"]
            configurations = set()

            for filename in files:
                parent = (project / filename).parent

                while parent.is_relative_to(project):
                    found = next((parent / n for n in ("phpcs.xml", ".phpcs.xml", "phpcs.xml.dist", ".phpcs.xml.dist") if (parent / n).is_file()), None)

                    if found:
                        configurations.add(found.relative_to(project).as_posix())
                        break

                    if parent == project:
                        break
                    parent = parent.parent
            item["configuration"] = [config_evidence(project, p, spec.phpcs["label"]) for p in sorted(configurations)] or [config_evidence(project, None, spec.phpcs["label"])]
        else:
            env["LINT_PHPSTAN_TOOLS"] = root

            if check in {"phpstan", "deadcode"}:
                configs = tuple(d + n for d in spec.phpstan["config_dirs"] for n in ("phpstan.neon", "phpstan.neon.dist"))
                config = next((name for name in configs if (project / name).is_file()), None)
                item["configuration"] = config_evidence(project, config, spec.phpstan["label"])

                if item["source"] == "profile" and not runner.exists(runner.path("vendor/autoload.php")):
                    raise ValueError(spec.phpstan["autoload_error"])

                if not config and not runner.exists(root + "/vendor/" + spec.phpstan["extension"]):
                    raise ValueError(f"PHPStan needs project configuration or the {spec.phpstan['extension_name']} extension")

                if check == "deadcode" and not runner.exists(root + "/vendor/shipmonk/dead-code-detector/rules.neon"):
                    raise ValueError("Dead-code detector is missing")
            elif check in spec.extra_checks:
                item["configuration"] = spec.extra_checks[check].configure(project, config_evidence)
            else:
                config = next((n for n in ("phpmd.xml", "phpmd.xml.dist", ".phpmd.xml") if (project / n).is_file()), None)
                item["configuration"] = config_evidence(project, config, spec.phpmd["label"])

    if check == "syntax" and any(Path(p).suffix in {".yml", ".yaml"} for p in files):
        autoload = runner.root + "/vendor/autoload.php"
        source = "project"

        if runner.exists(autoload):
            status, _, _ = runner.exec(["php", "-r", 'require $argv[1]; exit(class_exists($argv[2]) ? 0 : 1);', "--", autoload, spec.yaml["parser"]])

            if status not in {0, 1}:
                raise ValueError("Project autoloader failed; refusing parser fallback")
        else:
            status = 1

        if status:
            autoload, source = managed_bundle(runner, spec) + "/vendor/autoload.php", "profile"

            if php(runner, 'require $argv[1]; echo class_exists($argv[2]) ? "yes" : "no";', autoload, spec.yaml["parser"]) != "yes":
                raise ValueError("Managed YAML parser is unavailable")
        env["LINT_YAML_AUTOLOAD"] = autoload
        parser_version = php(runner, 'require $argv[1]; echo class_exists("Composer\\InstalledVersions") && Composer\\InstalledVersions::isInstalled($argv[2]) ? Composer\\InstalledVersions::getPrettyVersion($argv[2]) : "unknown";', autoload, spec.yaml["package"])
        tools.append(dict(name="yaml-parser", path=autoload, source=source, version=parser_version,
                          identity=php(runner, 'echo hash_file("sha256",$argv[1]);', autoload)))
    runtimes = []

    if needs_php(check, spec):
        runtimes.append("php")

    if check in {"composer", "audit"}:
        runtimes.append("composer")

    for binary in runtimes:
        tools.append(versioned(runner, binary, binary, "runner"))

    return dict(tools=tools, environment=env)


def plan(check, project, files, runner, node_config, spec):
    if needs_php(check, spec) and not runner.command_available("php"):
        raise ValueError("PHP is missing in the selected runner")

    if check in {"composer", "audit"} and not runner.command_available("composer"):
        raise ValueError("Composer is missing in the selected runner")

    return selection(check, project, files, runner, spec)


def applies(files, spec):
    paths = [Path(p) for p in files]
    php = any(is_php(spec, p) for p in paths)

    return {"phpcs": php, "phpstan": php, "syntax": php or any(p.suffix in {".yml", ".yaml"} for p in paths),
            "composer": any(p.name in {"composer.json", "composer.lock"} for p in paths),
            "phpmd": php, "audit": any(p.name == "composer.lock" for p in paths), "deadcode": php}


def claims(check, spec):
    extra = spec.extra_checks.get(check)

    return check in PHP_CHECKS or bool(extra and (extra.php or extra.tool))
