import re
import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parents[1] / "scripts"))
sys.path.insert(0, str(DIRECTORY / "scripts"))
import go_lint as lint
import go_setup

GO_DEBUG = re.compile(r"\bspew\.(?:Dump|Printf)\(|\bpp\.Print(?:ln)?\(|\b(?:log|fmt)\.Print(?:f|ln)?\(\"DEBUG|(?<![\w.])println\(")
SCRIPT_DEBUG = re.compile(r"\bconsole\.log\(|\bdebugger;")


class GoSpec:
    id = "go"
    name = "Go"
    directory = DIRECTORY
    providers = ()
    code_extensions = {".go"}
    excluded = {"vendor", "node_modules", "testdata", ".git"}
    excluded_prefixes = ()
    core_configs = ()
    core_prefixes = ()
    debug_pattern = re.compile(GO_DEBUG.pattern + "|" + SCRIPT_DEBUG.pattern)
    runner = dict(services=("app", "api", "go"), root="/app")
    bundle_source = DIRECTORY / "tools"
    bundle_component = "profiles/go"
    bundle_binaries = dict(go=("golangci-lint", "govulncheck"), node=("eslint", "stylelint", "jscpd"))
    custom_code = dict(name="", parents=set(), skip=set(), paths=(".",))
    parsers = lint.PARSERS
    dup = dict(formats="go,javascript,scss", extensions="go:go;javascript:js,mjs,cjs;scss:scss",
               ignore=",**/vendor/**,**/testdata/**,**/*_test.go")
    extra_checks = lint.EXTRA

    def debug_match(self, file, text):
        if not file.endswith(".go"):
            return SCRIPT_DEBUG.search(text)

        if file.endswith("_test.go") or text.lstrip().startswith("//"):
            return None

        return GO_DEBUG.search(text)

    def compatibility(self, runner):
        return go_setup.compatible(runner)


SPEC = GoSpec()
