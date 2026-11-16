import json
import re
import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parent / "_shared/php"))
from php_provider import PHP, Extra
from php_runtime import is_php, php
from core_checks import Parser

MINIMUM_MAJOR = 12
RECTOR_CONFIG = (
    '<?php use Rector\\Config\\RectorConfig; use RectorLaravel\\Set\\LaravelSetList; '
    'return RectorConfig::configure()->withSets([LaravelSetList::LARAVEL_CODE_QUALITY]);')


def php_applies(paths):
    return any(is_php(SPEC, p) for p in paths)


def project_config(name, label):
    return lambda project, evidence: evidence(project, name if (project / name).is_file() else None, label)


def pint_report(lint, data):
    reported = False

    for entry in data["files"] if data.get("result") == "fail" else []:
        reported = True
        lint.add(entry["path"], 0, "Style differs from the Pint rules: " + ", ".join(entry.get("fixers", [])), "error", "pint")

    return reported


def pint_run(lint):
    tool = next(t for t in lint.selected["tools"] if t["name"] == "pint")
    args = [tool["path"], "--test", "--format=json"]

    if tool["configuration"]["source"] != "project":
        args.append("--preset=laravel")
    lint.parse("pint", *lint.call([*args, *[f for f in lint.files if is_php(lint.spec, f)]]))


def rector_report(lint, data):
    reported = False

    if data.get("errors"):
        raise ValueError("; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in data["errors"]))

    for entry in data.get("file_diffs", []):
        reported = True
        names = [n.rsplit("\\", 1)[-1] for n in entry.get("applied_rectors", [])]
        lint.add(entry["file"], 0, "Rector would change this file: " + ", ".join(names), "warning", "rector")

    return reported


def rector_run(lint):
    tool = next(t for t in lint.selected["tools"] if t["name"] == "rector")
    conf = tool["configuration"]
    config = lint.runner.path(conf["path"]) if conf["source"] == "project" else lint.temporary("rector.php", RECTOR_CONFIG)
    autoload = lint.runner.path("vendor/autoload.php")
    files = [f for f in lint.files if is_php(lint.spec, f)]
    lint.parse("rector", *lint.call([tool["path"], "process", "--dry-run", "--no-progress-bar", "--output-format=json",
                                     "--config", config, "--autoload-file", autoload, *files]))


class LaravelSpec:
    id = "laravel"
    name = "Laravel"
    directory = DIRECTORY
    php_extensions = {".php"}
    template_suffixes = (".blade.php",)
    providers = (PHP,)
    code_extensions = {".php"}
    excluded = {"vendor", "node_modules", "storage"}
    excluded_prefixes = ("bootstrap/cache/", "public/build/")
    core_configs = ()
    core_prefixes = ()
    debug_pattern = re.compile(r"\b(dd|ddd|dump|ray|var_dump|dump_server)\(|\bconsole\.log\(|\bdebugger;|\bprint_r\((?![^)]*(TRUE|true)\))")
    yaml = dict(parser="Symfony\\Component\\Yaml\\Yaml", exception="Symfony\\Component\\Yaml\\Exception\\ParseException",
                package="symfony/yaml")
    runner = dict(services=("laravel.test", "app", "php"), root="/var/www/html")
    bundle_source = DIRECTORY / "tools"
    bundle_component = "profiles/laravel"
    bundle_binaries = dict(composer=("phpstan", "pint", "phpmd", "rector"), node=("eslint", "stylelint", "jscpd"))
    custom_code = dict(name="app", parents=set(), skip=set(), paths=("app", "routes", "resources", "database", "config"))
    parsers = {"pint": Parser({0, 1}, "{", pint_report), "rector": Parser({0, 2}, "{", rector_report)}
    phpstan = dict(label="Larastan level 5", level=5, config_dirs=("",),
                   extension="larastan/larastan/extension.neon", extension_name="Larastan",
                   includes=("larastan/larastan/extension.neon",),
                   autoload_error="Managed PHPStan needs the target Laravel project's Composer autoloader")
    phpmd = dict(label="PHPMD codesize + unusedcode", suffixes="php",
                 ruleset='<ruleset name="Ready Check"><rule ref="rulesets/unusedcode.xml"/><rule ref="rulesets/codesize.xml"/></ruleset>')
    dup = dict(formats="php,javascript,scss", extensions="php:php;javascript:js,mjs,cjs;scss:scss")
    extra_checks = dict(
        pint=Extra(php_applies, pint_run, tool="pint", php=True, configure=project_config("pint.json", "Laravel Pint, laravel preset")),
        rector=Extra(php_applies, rector_run, tool="rector", php=True, configure=project_config("rector.php", "Rector with the Laravel code-quality set")))

    def major(self, project):
        lock = project / "composer.lock"

        if lock.is_file():
            data = json.loads(lock.read_text(encoding="utf-8"))

            for package in data.get("packages", []) + data.get("packages-dev", []):
                match = package["name"] == "laravel/framework" and re.match(r"v?(\d+)\.", package["version"])

                if match:
                    return int(match[1])

        raise ValueError("Managed Laravel tools need an installed Laravel version (composer.lock)")

    def compatibility(self, runner):
        major = self.major(runner.project)

        if major < MINIMUM_MAJOR:
            raise ValueError(f"Managed tools currently support Laravel {MINIMUM_MAJOR} and newer, found Laravel {major}")
        version = int(php(runner, "echo PHP_VERSION_ID;"))

        if version < 80200:
            raise ValueError("Managed tools/installed Laravel need runner PHP 8.2 or newer")

        return dict(laravel_major=major, php_id=version)


SPEC = LaravelSpec()
