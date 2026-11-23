import json
import re
import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parent / "_shared/php"))
sys.path.insert(0, str(DIRECTORY / "scripts"))
from php_provider import PHP, Extra
from php_runtime import php
from phpstan_bootstrap import handle_report

PHP_EXTENSIONS = {".php", ".module", ".inc", ".install", ".theme", ".profile", ".engine", ".test"}
CORE_FILE = "core/lib/Drupal.php"
CONFIG_PATH = re.compile(r"(?:^|/)config/(install|optional|schema)/")
TWIG_RULESET = (
    '<?php $r=new TwigCsFixer\\Ruleset\\Ruleset(); $r->addStandard(new TwigCsFixer\\Standard\\TwigCsFixer()); '
    '$r->removeRule(TwigCsFixer\\Rules\\Function\\IncludeFunctionRule::class); $r->removeRule(TwigCsFixer\\Rules\\Literal\\CompactHashRule::class); '
    '$c=new TwigCsFixer\\Config\\Config(); $c->setRuleset($r); $c->setCacheFile(NULL); return $c;')


def config_applies(paths):
    return any(p.suffix in {".yml", ".yaml"} and CONFIG_PATH.search(p.as_posix()) for p in paths)


def config_run(lint):
    for file in lint.files:
        if Path(file).suffix not in {".yml", ".yaml"} or not CONFIG_PATH.search(file):
            continue

        for line, text in enumerate((lint.project / file).read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"^(uuid|_core):", text):
                lint.add(file, line, f"Remove site-specific '{text.split(':')[0]}' from module config")


def twig_applies(paths):
    return any(p.suffix == ".twig" for p in paths)


def twig_configure(project, evidence):
    config = next((n for n in (".twig-cs-fixer.php", ".twig-cs-fixer.dist.php") if (project / n).is_file()), None)
    return evidence(project, config, "TwigCsFixer with Drupal include/hash syntax")


def twig_run(lint):
    tool = next(t for t in lint.selected["tools"] if t["name"] == "twig-cs-fixer")
    conf = tool["configuration"]
    config = lint.runner.path(conf["path"]) if conf["source"] == "project" else lint.temporary("twig.php", TWIG_RULESET)
    files = [f for f in lint.files if f.endswith(".twig")]
    lint.parse("checkstyle", *lint.call([tool["path"], "lint", "-c", config, "--report=checkstyle", *files]), label="twig")


class DrupalSpec:
    id = "drupal"
    name = "Drupal"
    directory = DIRECTORY
    php_extensions = PHP_EXTENSIONS
    providers = (PHP,)
    code_extensions = PHP_EXTENSIONS | {".twig"}
    excluded = {"vendor", "node_modules", "contrib", "libraries", "dist", "files", "storybook-static"}
    core_configs = (".eslintrc", ".eslintrc.json", ".stylelintrc", ".stylelintrc.json")
    debug_pattern = re.compile(r"\b(var_dump|dump|dpm|dvm|dsm|kint|ksm|kpr|dd|ddm|ddebug_backtrace|xdebug_break|die)\(|\bconsole\.log\(|\bdebugger;|\bprint_r\((?![^)]*(TRUE|true)\))")
    yaml = dict(parser="Symfony\\Component\\Yaml\\Yaml", exception="Symfony\\Component\\Yaml\\Exception\\ParseException",
                package="symfony/yaml")
    runner = dict(services=("php",), root="/var/www/html")
    bundle_source = DIRECTORY / "tools"
    bundle_component = "profiles/drupal"
    bundle_binaries = dict(composer=("phpcs", "phpstan", "twig-cs-fixer", "phpmd"), node=("eslint", "stylelint", "jscpd"))
    custom_code = dict(name="custom", parents={"modules", "themes", "profiles"}, skip={"core"})
    phpcs = dict(label="Drupal + DrupalPractice", standards=("Drupal", "DrupalPractice"),
                 extensions="php,module,inc,install,test,profile,theme,engine",
                 installed_paths=("drupal/coder/coder_sniffer", "slevomat/coding-standard", "sirbrillig/phpcs-variable-analysis"))
    phpstan = dict(label="phpstan-drupal level 3", level=3, config_dirs=("", "web/", "docroot/", "html/"),
                   handle_report=handle_report,
                   extension="mglaman/phpstan-drupal/extension.neon", extension_name="phpstan-drupal",
                   includes=("mglaman/phpstan-drupal/extension.neon", "mglaman/phpstan-drupal/rules.neon",
                             "phpstan/phpstan-deprecation-rules/rules.neon"),
                   autoload_error="Managed PHPStan needs the target Drupal project's Composer autoloader")
    phpmd = dict(label="PHPMD codesize + unusedcode excluding hook parameters",
                 suffixes="php,module,inc,install,theme,profile,engine,test",
                 ruleset='<ruleset name="Ready Check"><rule ref="rulesets/unusedcode.xml"><exclude name="UnusedFormalParameter"/></rule><rule ref="rulesets/codesize.xml"/></ruleset>')
    dup = dict(formats="php,javascript,twig,scss",
               extensions="php:php,module,inc,install,theme,profile,engine;javascript:js,mjs,cjs;twig:twig;scss:scss")
    extra_checks = dict(config=Extra(config_applies, config_run),
                        twig=Extra(twig_applies, twig_run, tool="twig-cs-fixer", php=True, configure=twig_configure))

    @property
    def core_prefixes(self):
        profile = json.loads(DIRECTORY.joinpath("profile.json").read_text(encoding="utf-8"))
        return tuple(p.removesuffix("lib/Drupal.php") for p in profile["detection"]["core_paths"])

    def major(self, project):
        for relative in ("web", "docroot", "html", "."):
            path = project / relative / CORE_FILE

            if path.is_file():
                match = re.search(r"const VERSION\s*=\s*['\"](\d+)\.", path.read_text(encoding="utf-8"))

                if match:
                    return int(match[1])

        lock = project / "composer.lock"

        if lock.is_file():
            data = json.loads(lock.read_text(encoding="utf-8"))

            for package in data.get("packages", []) + data.get("packages-dev", []):
                if package["name"] == "drupal/core":
                    match = re.match(r"v?(\d+)\.", package["version"])

                    if match:
                        return int(match[1])

        raise ValueError("Managed Drupal tools need an installed Drupal version (core file or composer.lock)")

    def compatibility(self, runner):
        major = self.major(runner.project)

        if major not in {10, 11}:
            raise ValueError(f"Managed tools currently support Drupal 10/11, found Drupal {major}")

        version = int(php(runner, "echo PHP_VERSION_ID;"))
        minimum = 80300 if major == 11 else 80200

        for relative in ("web", "docroot", "html", "."):
            path = runner.project / relative / CORE_FILE

            if path.is_file():
                match = re.search(r"const MINIMUM_PHP\s*=\s*['\"](\d+)\.(\d+)\.(\d+)", path.read_text(encoding="utf-8"))

                if match:
                    parts = list(map(int, match.groups()))
                    minimum = max(minimum, parts[0] * 10000 + parts[1] * 100 + parts[2])

        if version < minimum:
            raise ValueError(f"Managed tools/installed Drupal need runner PHP {minimum // 10000}.{minimum // 100 % 100} or newer")

        return dict(drupal_major=major, php_id=version)


SPEC = DrupalSpec()
