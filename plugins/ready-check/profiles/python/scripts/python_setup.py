import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "_shared/core"))
sys.path.insert(0, str(HERE))
from core_setup import setup as core_setup
import python_tools

MINIMUM = (3, 10)


class PipBundle:
    binaries = ("python3",)

    def __init__(self, spec):
        self.spec = spec

    def venv(self, context):
        return context.destination + "/venv"

    def environment(self, context):
        env = dict.fromkeys(("PYTHONPATH", "PYTHONHOME", "PIP_USER", "PIP_TARGET", "PIP_PREFIX", "PIP_REQUIRE_VIRTUALENV"))
        env.update(PIP_CACHE_DIR=str(context.path_type(context.root) / "pip-cache"), PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1")

        return env

    def ready(self, context):
        return all(context.runner.exists(self.venv(context) + "/bin/" + name) for name in self.spec.bundle_binaries["pip"])

    def install(self, context):
        env = self.environment(context)
        python = self.venv(context) + "/bin/python"
        context.call(["python3", "-m", "venv", "--copies", "--clear", self.venv(context)], env)
        context.call([python, "-m", "pip", "install", "--require-hashes", "--no-deps", "-r", context.destination + "/requirements.txt"], env)

    def finalize(self, context):
        context.call([self.venv(context) + "/bin/python", "-m", "pip", "check"], self.environment(context))

    def tools(self, context):
        return [python_tools.item(context.runner, self.venv(context), name, "profile", self.spec)
                for name in self.spec.bundle_binaries["pip"]]


def compatible(runner):
    status, stdout, stderr = runner.exec(["python3", "--version"], timeout=30)
    match = re.search(r"Python (\d+)\.(\d+)\.(\d+)", (stdout + stderr).decode(errors="replace"))

    if status or not match:
        raise ValueError("Python 3 is missing in the selected runner")

    version = tuple(map(int, match.groups()))

    if version[:2] < MINIMUM:
        raise ValueError("Managed Python tools need runner Python {}.{} or newer, found {}.{}".format(*MINIMUM, *version[:2]))

    return dict(python="{}.{}.{}".format(*version))


def setup(project, host_root, override, dry_run, timeout, spec):
    return core_setup(project, host_root, override, dry_run, timeout, spec, (PipBundle(spec),))
