import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "_shared/core"))
sys.path.insert(0, str(HERE))
from core_setup import setup as core_setup
from core_toolchain import versioned
import go_tools

VERSION = re.compile(r"go(\d+)\.(\d+)(?:\.(\d+))?")
MODULE = re.compile(r"^\s*mod\s+(\S+)\s+(\S+)\s+(h1:\S+)\s*$", re.M)


def minimum():
    return tuple(int(part) for part in go_tools.manifest()["go_minimum"].split("."))


class GoBundle:
    binaries = ("go",)

    def __init__(self, spec):
        self.spec = spec

    def bin(self, context, name):
        return context.destination + "/bin/" + go_tools.executable(context.runner, name)

    def environment(self, context):
        return dict(GOBIN=context.destination + "/bin", GOFLAGS="-mod=mod", GOTOOLCHAIN="local", GOWORK="off")

    def ready(self, context):
        return all(context.runner.exists(self.bin(context, name)) for name in self.spec.bundle_binaries["go"])

    def install(self, context):
        env = self.environment(context)

        for name in self.spec.bundle_binaries["go"]:
            pinned = go_tools.manifest()["tools"][name]
            context.call(["go", "install", pinned["module"] + "@" + pinned["version"]], env)

    def finalize(self, context):
        for name in self.spec.bundle_binaries["go"]:
            pinned = go_tools.manifest()["tools"][name]
            info = context.call(["go", "version", "-m", self.bin(context, name)])
            found = {m[1]: (m[2], m[3]) for m in MODULE.finditer(info)}

            if found.get(pinned["sum_module"]) != (pinned["version"], pinned["sum"]):
                raise ValueError(f"Installed {name} does not match the pinned module checksum; the binary was not accepted")

    def tools(self, context):
        return [versioned(context.runner, name, self.bin(context, name), "profile", spec=self.spec)
                for name in self.spec.bundle_binaries["go"]]


def compatible(runner):
    status, stdout, stderr = runner.exec(["go", "version"], timeout=30)
    match = VERSION.search((stdout + stderr).decode(errors="replace"))

    if status or not match:
        raise ValueError("Go is missing in the selected runner")
    version = tuple(int(part or 0) for part in match.groups())

    if version < minimum():
        raise ValueError("Managed Go tools need runner Go {} or newer, found {}; toolchains are never downloaded".format(
            ".".join(map(str, minimum())), ".".join(map(str, version))))

    return dict(go=".".join(map(str, version)))


def setup(project, host_root, override, dry_run, timeout, spec):
    return core_setup(project, host_root, override, dry_run, timeout, spec, (GoBundle(spec),))
