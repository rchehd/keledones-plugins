import json
import re
import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parent / "_shared/php"))
sys.path.insert(0, str(DIRECTORY / "scripts"))
from php_provider import PHP, Extra
from php_runtime import php
import symfony_lint as lint

MINIMUM = (7, 4)


class SymfonySpec:
    id = "symfony"
    name = "Symfony"
    directory = DIRECTORY
    php_extensions = {".php"}
    providers = (PHP,)
    code_extensions = {".php", ".twig"}
    excluded = {"vendor", "var", "node_modules"}
    excluded_prefixes = ("public/build/", "public/bundles/")
    core_configs = ()
    core_prefixes = ()
    debug_pattern = re.compile(r"\b(dd|dump|var_dump)\(|\bconsole\.log\(|\bdebugger;|\bprint_r\((?![^)]*(TRUE|true)\))")
    yaml = dict(parser="Symfony\\Component\\Yaml\\Yaml", exception="Symfony\\Component\\Yaml\\Exception\\ParseException",
                package="symfony/yaml", flags=512)
    runner = dict(services=("php", "app"), root="/app")
    bundle_source = DIRECTORY / "tools"
    bundle_component = "profiles/symfony"
    bundle_binaries = dict(composer=("phpstan", "php-cs-fixer", "phpmd"), node=("eslint", "stylelint", "jscpd"))
    custom_code = dict(name="app", parents=set(), skip=set(), paths=("src", "config", "migrations", "assets"))
    parsers = lint.PARSERS
    phpstan = dict(label="phpstan-symfony level 5", level=5, config_dirs=("",),
                   extension="phpstan/phpstan-symfony/extension.neon", extension_name="phpstan-symfony",
                   includes=("phpstan/phpstan-symfony/extension.neon",),
                   optional_includes=(("doctrine/orm", "phpstan/phpstan-doctrine/extension.neon"),),
                   autoload_error="Managed PHPStan needs the target Symfony project's Composer autoloader")
    phpmd = dict(label="PHPMD codesize + unusedcode", suffixes="php",
                 ruleset='<ruleset name="Ready Check"><rule ref="rulesets/unusedcode.xml"/><rule ref="rulesets/codesize.xml"/></ruleset>')
    dup = dict(formats="php,javascript,scss", extensions="php:php;javascript:js,mjs,cjs;scss:scss")
    extra_checks = dict(
        csfixer=Extra(lint.php_applies, lint.csfixer_run, tool="php-cs-fixer", php=True, configure=lint.csfixer_config),
        container=Extra(lint.container_applies, lint.container_run, php=True),
        yaml=Extra(lint.yaml_applies, lint.json_lint("lint:yaml", lint.yaml_applies), php=True),
        twig=Extra(lint.twig_applies, lint.json_lint("lint:twig", lint.twig_applies), php=True),
        xliff=Extra(lint.xliff_applies, lint.json_lint("lint:xliff", lint.xliff_applies), php=True),
        schema=Extra(lint.schema_applies, lint.schema_run, php=True))

    def version(self, project):
        lock = project / "composer.lock"

        if lock.is_file():
            data = json.loads(lock.read_text(encoding="utf-8"))

            for package in data.get("packages", []) + data.get("packages-dev", []):
                match = package["name"] == "symfony/framework-bundle" and re.match(r"v?(\d+)\.(\d+)", package["version"])

                if match:
                    return int(match[1]), int(match[2])

        raise ValueError("Managed Symfony tools need an installed Symfony version (composer.lock)")

    def compatibility(self, runner):
        version = self.version(runner.project)

        if version < MINIMUM:
            raise ValueError("Managed tools currently support Symfony {}.{} and newer, found Symfony {}.{}".format(*MINIMUM, *version))
        php_id = int(php(runner, "echo PHP_VERSION_ID;"))

        if php_id < 80200:
            raise ValueError("Managed tools/installed Symfony need runner PHP 8.2 or newer")

        return dict(symfony="{}.{}".format(*version), php_id=php_id)


SPEC = SymfonySpec()
