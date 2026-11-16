import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from core_setup import setup as core_setup
from core_toolchain import versioned


class ComposerBundle:
    binaries = ("composer",)

    def __init__(self, spec):
        self.spec = spec

    def environment(self, context):
        env = dict.fromkeys(("COMPOSER", "COMPOSER_VENDOR_DIR", "COMPOSER_BIN_DIR", "COMPOSER_AUTH", "COMPOSER_IGNORE_PLATFORM_REQS"))
        env.update(COMPOSER_HOME=str(context.path_type(context.root) / "composer-home"),
                   COMPOSER_CACHE_DIR=str(context.path_type(context.root) / "composer-cache"))

        return env

    def ready(self, context):
        return all(context.runner.exists(context.destination + "/vendor/bin/" + name) for name in self.spec.bundle_binaries["composer"])

    def install(self, context):
        context.call(["composer", "install", "--no-plugins", "--no-scripts", "--no-interaction", "--prefer-dist"], self.environment(context))

    def finalize(self, context):
        context.call(["composer", "check-platform-reqs", "--no-plugins", "--no-scripts", "--no-interaction"], self.environment(context))

        if "phpcs" in self.spec.bundle_binaries["composer"]:
            paths = ",".join(context.destination + "/vendor/" + name for name in self.spec.phpcs["installed_paths"])
            context.call([context.destination + "/vendor/bin/phpcs", "--config-set", "installed_paths", paths])

    def tools(self, context):
        return [versioned(context.runner, name, context.destination + "/vendor/bin/" + name, "profile", spec=self.spec)
                for name in self.spec.bundle_binaries["composer"]]


def setup(project, host_root, override, dry_run, timeout, spec):
    return core_setup(project, host_root, override, dry_run, timeout, spec, (ComposerBundle(spec),))
