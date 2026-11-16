import json
import re
import sys
from pathlib import Path, PurePosixPath

DIRECTORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DIRECTORY.parents[1] / "scripts"))
sys.path.insert(0, str(DIRECTORY / "scripts"))
import detect
import python_lint as lint
import python_setup

PYTHON_DEBUG = re.compile(r"\bbreakpoint\(\)|\b(?:i?pdb|pudb)\.set_trace\(|\bpytest\.set_trace\(")
SCRIPT_DEBUG = re.compile(r"\bconsole\.log\(|\bdebugger;")
PRINT = re.compile(r"(?<![\w.])print\(")


def quiet(file):
    path = PurePosixPath(file)
    return bool({"tests", "test"} & set(path.parts[:-1])) or path.name.startswith("test_") or path.name.endswith("_test.py") or \
        path.name == "conftest.py" or "management/commands" in file


class PythonSpec:
    id = "python"
    name = "Python"
    directory = DIRECTORY
    providers = ()
    code_extensions = {".py"}
    excluded = {".venv", "venv", "__pycache__", ".tox", "node_modules", "build", "dist", ".mypy_cache", ".ruff_cache"}
    excluded_prefixes = ()
    core_configs = ()
    core_prefixes = ()
    debug_pattern = re.compile(PYTHON_DEBUG.pattern + "|" + PRINT.pattern + "|" + SCRIPT_DEBUG.pattern)
    runner = dict(services=("web", "app", "django"), root="/app")
    bundle_source = DIRECTORY / "tools"
    bundle_component = "profiles/python"
    bundle_binaries = dict(pip=("ruff", "mypy", "bandit", "pip-audit"), node=("eslint", "stylelint", "jscpd"))
    custom_code = dict(name="", parents=set(), skip=set(), paths=(".",))
    parsers = lint.PARSERS
    dup = dict(formats="python,javascript,scss", extensions="python:py;javascript:js,mjs,cjs;scss:scss",
               ignore=",**/.venv/**,**/venv/**,**/__pycache__/**,**/migrations/**,**/tests/**,**/test_*.py,**/build/**,**/.tox/**")
    extra_checks = lint.EXTRA

    def debug_match(self, file, text):
        if not file.endswith(".py"):
            return SCRIPT_DEBUG.search(text)

        if text.lstrip().startswith("#"):
            return None

        return PYTHON_DEBUG.search(text) or (PRINT.search(text) if not quiet(file) else None)

    def framework(self, project):
        return detect.framework(project, json.loads(DIRECTORY.joinpath("profile.json").read_text(encoding="utf-8")))

    def compatibility(self, runner):
        return python_setup.compatible(runner)


SPEC = PythonSpec()
