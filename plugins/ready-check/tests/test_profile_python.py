import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from helpers import write_fake_command

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
import detect
from core_main import applicable
from core_runner import Runner
from core_scope import lint_files
from profile_runtime import load_spec

CHECK = PLUGIN / "scripts/check-profile.py"
RUFF = '''#!/usr/bin/env python3
import json, os, sys
if "--version" in sys.argv:
    print("ruff 0.17.3")
    sys.exit(0)
if sys.argv[1] == "format":
    diff = "--- app.py\\n+++ app.py\\n@@ -1,3 +1,3 @@\\n x = 1\\n-import  os\\n+import os\\n print(x)\\n"
    sys.stdout.buffer.write(diff.replace("\\n", "\\r\\n").encode())
    sys.exit(1)
root = os.getcwd()
print(json.dumps([
    {"code": "F401", "message": "`os` imported but unused", "filename": root + "/app.py", "location": {"row": 2, "column": 8}},
    {"code": "E722", "message": "Do not use bare `except`", "filename": root + "/app.py", "location": {"row": 1, "column": 1}}]))
sys.exit(1)
'''
BANDIT = '''#!/usr/bin/env python3
import json, sys
if "--version" in sys.argv:
    print("bandit 1.9.4\\n  python version = 3.12")
    sys.exit(0)
print(json.dumps({"errors": [], "results": [
    {"filename": "./app.py", "line_number": 3, "issue_severity": "HIGH", "issue_text": "SQL built from a string", "test_id": "B608", "test_name": "hardcoded_sql_expressions"},
    {"filename": "./app.py", "line_number": 1, "issue_severity": "LOW", "issue_text": "Old", "test_id": "B101", "test_name": "assert_used"}]}))
sys.exit(1)
'''
MYPY = '''#!/usr/bin/env python3
import sys
if "--version" in sys.argv:
    print("mypy 2.4.1 (compiled: yes)")
    sys.exit(0)
print("app.py:3:5: error: Incompatible types in assignment  [assignment]")
print("app.py:3:5: note: See the docs")
print("app.py:1:1: error: Old problem  [misc]")
sys.exit(1)
'''
MANAGE = '''import os, sys
mode = os.environ.get("FAKE_DJANGO", "ok")
command = sys.argv[1]
if mode == "import":
    sys.stderr.write("Traceback (most recent call last):\\nImportError: Couldn't import Django.\\n")
    sys.exit(1)
if command == "check":
    if mode == "errors":
        sys.stderr.write("SystemCheckError: System check identified some issues:\\n\\nERRORS:\\nnotes.Note: (models.E001) Broken field.\\n\\nWARNINGS:\\nnotes.Note: (models.W042) Auto-created primary key.\\n\\nSystem check identified 2 issues (0 silenced).\\n")
        sys.exit(1)
    if mode == "warn":
        print("System check identified some issues:\\n\\nWARNINGS:\\nnotes.Note: (models.W042) Auto-created primary key.\\n\\nSystem check identified 1 issue (0 silenced).")
        sys.exit(0)
    print("System check identified no issues (0 silenced).")
    sys.exit(0)
if mode == "migrate":
    print("Migrations for 'notes':\\n  notes/migrations/0002_note_title.py\\n    + Add field title to note")
    sys.exit(1)
print("No changes detected")
'''
CHANGED = "x = 1\nimport os\nprint(x)\n"


class DetectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if isinstance(data, dict) else data)

    def test_django_application(self):
        self.write("manage.py", "#!/usr/bin/env python\n")
        self.write("requirements.txt", "Django==5.2.1\n")
        found = detect.detect(self.root)
        self.assertEqual((found["profile"], found["name"], found["framework"], found["runner"]), ("python", "Python", "django", "local"))

    def test_django_dependency_alone_is_enough(self):
        self.write("pyproject.toml", '[project]\nname = "site"\ndependencies = ["django>=5.2", "django-environ"]\n')
        self.assertEqual(detect.detect(self.root)["framework"], "django")

    def test_fastapi_and_flask(self):
        self.write("requirements.txt", "fastapi==0.120.0\nuvicorn\n")
        self.assertEqual(detect.detect(self.root)["framework"], "fastapi")
        self.write("requirements.txt", "flask==3.1.0\n")
        self.assertEqual(detect.detect(self.root)["framework"], "flask")
        self.write("requirements.txt", "requests\n")
        self.assertIsNone(detect.detect(self.root)["framework"])

    def test_django_extras_are_not_django(self):
        self.write("requirements.txt", "django-environ==0.11\ndjangorestframework\n")
        self.assertIsNone(detect.detect(self.root)["framework"])

    def test_php_applications_are_never_python(self):
        self.write("requirements.txt", "Django==5.2.1\n")
        self.write("composer.json", {"require": {"laravel/framework": "^12.0"}})
        self.assertEqual(detect.detect(self.root)["profile"], "laravel")
        self.write("composer.json", {"require": {"symfony/framework-bundle": "^7.4"}})
        self.assertEqual(detect.detect(self.root)["profile"], "symfony")
        self.write("composer.json", {"require": {"drupal/core-recommended": "^11"}})
        self.write("web/core/lib/Drupal.php", "<?php\n")
        self.assertEqual(detect.detect(self.root)["profile"], "drupal")


class InterpreterTest(unittest.TestCase):
    def test_managed_mypy_gets_the_interpreter_behind_uv_or_poetry(self):
        sys.path.insert(0, str(PLUGIN / "profiles/python/scripts"))
        import python_tools

        class Stub:
            def exec(self, argv, timeout=15):
                self.argv = argv
                return 0, b"Installing...\n/project/.uv-env/bin/python\n", b""

        runner = Stub()
        with patch.object(python_tools, "resolve", return_value=(["uv", "run", "--no-sync", "python"], "uv", None)):
            self.assertEqual(python_tools.executable(runner, Path(".")), "/project/.uv-env/bin/python")
        self.assertEqual(runner.argv[:4], ["uv", "run", "--no-sync", "python"])
        with patch.object(python_tools, "resolve", return_value=(["/p/.venv/bin/python"], "project", "/p/.venv/bin/python")):
            self.assertEqual(python_tools.executable(runner, Path(".")), "/p/.venv/bin/python")


class SpecTest(unittest.TestCase):
    def setUp(self):
        self.spec = load_spec("python")

    def test_runner_defaults_choose_web_service_and_app_root(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            for name in ("LINT_RUNNER", "LINT_SERVICE", "LINT_CONTAINER_ROOT"):
                os.environ.pop(name, None)
            project = Path(folder)
            (project / "compose.yaml").write_text("services:\n  db:\n    image: postgres\n  web:\n    build: .\n")
            runner = Runner(project, {}, self.spec.runner)
            self.assertEqual((runner.name, runner.service, runner.root), ("compose", "web", "/app"))

    def test_every_profile_check_is_implemented(self):
        profile = json.loads((PLUGIN / "profiles/python/profile.json").read_text())
        known = applicable(["app.py", "requirements.txt", "static/app.js"], self.spec)
        self.assertEqual({c["id"] for c in profile["checks"]} - set(known), set())

    def test_checks_apply_only_to_their_inputs(self):
        def status(*files):
            known = applicable(list(files), self.spec)
            return {name: known[name] for name in ("ruff", "format", "syntax", "mypy", "django", "migrations", "bandit", "audit")}

        self.assertFalse(any(status("README.md").values()))
        self.assertEqual({k for k, v in status("app/views.py").items() if v}, {"ruff", "format", "syntax", "mypy", "django", "migrations", "bandit"})
        self.assertEqual({k for k, v in status("requirements-dev.txt").items() if v}, {"audit"})
        self.assertTrue(status("uv.lock")["audit"])

    def test_debug_matches_leftovers_in_app_code_only(self):
        def hit(file, text):
            return bool(self.spec.debug_match(file, text))

        for text in ("breakpoint()", "    print(q)", "import pdb; pdb.set_trace()", "ipdb.set_trace()"):
            self.assertTrue(hit("notes/views.py", text), text)

        for text in ("pprint(x)", "self.print(x)", "# print(x)", "blueprint(x)"):
            self.assertFalse(hit("notes/views.py", text), text)

        for file in ("tests/test_views.py", "notes/test_models.py", "notes/management/commands/seed.py", "conftest.py"):
            self.assertFalse(hit(file, "print(x)"), file)
            self.assertTrue(hit(file, "breakpoint()"), file)
        self.assertTrue(hit("static/app.js", "console.log(x)"))

    def test_generated_paths_are_not_linted(self):
        files = ["app.py", ".venv/lib/x.py", "venv/x.py", "build/x.py", "notes/__pycache__/x.py", "notes/migrations/0001_initial.py"]
        self.assertEqual(lint_files(files, self.spec.core_prefixes, self.spec), ["app.py", "notes/migrations/0001_initial.py"])


@unittest.skipUnless(shutil.which("git"), "Git is required")
class FakeToolsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("LINT_", "READY_CHECK_", "FAKE_"))}
        self.env.update(LINT_RUNNER="local", READY_CHECK_DATA_DIR=str(self.root / "data"))
        self.write("pyproject.toml", '[project]\nname = "site"\n\n[tool.ruff]\nline-length = 100\n')
        self.write(".gitignore", ".venv/\n")
        self.write("app.py", "x = 1\n")
        self.write("manage.py", MANAGE)
        self.write("README.md", "# App\n")
        self.git("init", "-b", "main")
        self.git("add", ".")
        self.git("-c", "user.name=F", "-c", "user.email=f@example.invalid", "commit", "-m", "Fixture")
        environment = self.project / ".venv"
        venv.EnvBuilder(with_pip=False).create(environment)
        windows = os.name == "nt"
        self.bin = environment / ("Scripts" if windows else "bin")
        python = self.bin / ("python.exe" if windows else "python")
        self.site_packages = Path(subprocess.check_output(
            [str(python), "-X", "utf8", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True, encoding="utf-8").strip())

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, check=True).stdout

    def write(self, name, content):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def tool(self, name, source):
        write_fake_command(self.bin / name, source)
        (self.site_packages / (name.replace("-", "_") + ".py")).write_text(source, encoding="utf-8")

    def static(self, mode=None):
        env = dict(self.env, **({"FAKE_DJANGO": mode} if mode else {}))
        process = subprocess.run([sys.executable, "-B", str(CHECK), "static", "--profile", "python", "--project", str(self.project),
                                  "--base", "main"], env=env, capture_output=True, text=True, encoding="utf-8")
        data = json.loads(process.stdout)

        if data.get("evidence_directory"):
            self.addCleanup(shutil.rmtree, data["evidence_directory"], True)
        return {c["id"]: c for c in data["checks"]}

    def test_ruff_findings_are_limited_to_changed_lines(self):
        self.tool("ruff", RUFF)
        self.write("app.py", CHANGED)
        ruff = self.static()["ruff"]
        self.assertEqual(ruff["status"], "FAIL", ruff)
        self.assertEqual([(f["file"], f["line"], f["source"]) for f in ruff["findings"]], [("app.py", 2, "F401")])
        self.assertEqual((ruff["tools"][0]["source"], ruff["tools"][0]["configuration"]["source"]), ("project", "project"))

    def test_ruff_format_diff_gives_a_file_level_finding(self):
        self.tool("ruff", RUFF)
        self.write("app.py", CHANGED)
        formatted = self.static()["format"]
        self.assertEqual(formatted["status"], "FAIL", formatted)
        self.assertEqual((formatted["findings"][0]["file"], formatted["findings"][0]["line"]), ("app.py", 2))

    def test_unparsable_ruff_output_is_incomplete(self):
        self.tool("ruff", '#!/usr/bin/env python3\nimport sys\n'
                          'if "--version" in sys.argv:\n    print("ruff 0.17.3")\n    sys.exit(0)\n'
                          'print("nonsense")\nsys.exit(1)\n')
        self.write("app.py", CHANGED)
        self.assertEqual(self.static()["ruff"]["status"], "INCOMPLETE")

    def test_missing_managed_tools_are_incomplete_not_pass(self):
        self.write("app.py", CHANGED)
        self.assertEqual(self.static()["bandit"]["status"], "INCOMPLETE")

    def test_bandit_severity_and_changed_lines(self):
        self.tool("bandit", BANDIT)
        self.write("app.py", CHANGED)
        bandit = self.static()["bandit"]
        self.assertEqual(bandit["status"], "FAIL", bandit)
        self.assertEqual([(f["line"], f["severity"], f["source"]) for f in bandit["findings"]], [(3, "error", "B608")])
        self.assertFalse(bandit["required"])

    def test_mypy_is_not_applicable_without_project_configuration(self):
        self.tool("mypy", MYPY)
        self.write("app.py", CHANGED)
        mypy = self.static()["mypy"]
        self.assertEqual(mypy["status"], "N/A", mypy)
        self.assertIn("not configured", mypy["reason"])

    def test_mypy_runs_when_the_project_configures_it(self):
        self.tool("mypy", MYPY)
        self.write("mypy.ini", "[mypy]\nstrict = true\n")
        self.write("app.py", CHANGED)
        mypy = self.static()["mypy"]
        self.assertEqual(mypy["status"], "FAIL", mypy)
        self.assertEqual([(f["line"], f["severity"]) for f in mypy["findings"]], [(3, "error")])

    def test_syntax_error_is_reported_with_its_line(self):
        self.write("app.py", "x = 1\ndef broken(:\n")
        syntax = self.static()["syntax"]
        self.assertEqual(syntax["status"], "FAIL", syntax)
        self.assertEqual((syntax["findings"][0]["file"], syntax["findings"][0]["line"]), ("app.py", 2))

    def test_valid_syntax_passes_without_writing_bytecode(self):
        self.write("app.py", CHANGED)
        self.assertEqual(self.static()["syntax"]["status"], "PASS")
        self.assertFalse((self.project / "__pycache__").exists())

    def test_debug_catches_app_code_and_ignores_tests(self):
        self.write("app.py", "x = 1\nbreakpoint()\nprint(x)\n")
        self.write("tests/test_app.py", "print('fine in tests')\n")
        debug = self.static()["debug"]
        self.assertEqual(debug["status"], "FAIL", debug)
        self.assertEqual(sorted((f["file"], f["line"]) for f in debug["findings"]), [("app.py", 2), ("app.py", 3)])

    def test_django_checks_pass_on_a_healthy_project(self):
        self.write("app.py", CHANGED)
        checks = self.static()
        self.assertEqual((checks["django"]["status"], checks["migrations"]["status"]), ("PASS", "PASS"), checks["django"])
        self.assertEqual(checks["django"]["tools"][0]["source"], "project")

    def test_django_check_errors_fail_and_warnings_stay_findings(self):
        self.write("app.py", CHANGED)
        django = self.static("errors")["django"]
        self.assertEqual(django["status"], "FAIL", django)
        self.assertEqual([(f["severity"], f["source"]) for f in django["findings"]], [("error", "models.E001"), ("warning", "models.W042")])
        warned = self.static("warn")["django"]
        self.assertEqual((warned["status"], warned["findings"][0]["severity"]), ("PASS", "warning"))

    def test_missing_migrations_fail(self):
        self.write("app.py", CHANGED)
        migrations = self.static("migrate")["migrations"]
        self.assertEqual(migrations["status"], "FAIL", migrations)
        self.assertEqual(migrations["findings"][0]["file"], "notes/migrations/0002_note_title.py")
        self.assertIn("Add field title", migrations["findings"][0]["message"])

    def test_unbootable_django_is_incomplete_not_pass(self):
        self.write("app.py", CHANGED)
        checks = self.static("import")

        for name in ("django", "migrations"):
            self.assertEqual(checks[name]["status"], "INCOMPLETE", checks[name])

    def test_django_checks_are_not_applicable_without_manage_py(self):
        (self.project / "manage.py").unlink()
        self.write("app.py", CHANGED)
        checks = self.static()

        for name in ("django", "migrations"):
            self.assertEqual(checks[name]["status"], "N/A", checks[name])

    def test_checks_are_not_applicable_when_inputs_did_not_change(self):
        self.write("README.md", "# Changed\n")
        checks = self.static()

        for name in ("ruff", "format", "syntax", "mypy", "django", "migrations", "bandit", "audit"):
            self.assertEqual(checks[name]["status"], "N/A", checks[name])


class RuffFormatScopeTest(unittest.TestCase):
    DIFF = ("--- a.py\n+++ a.py\n@@ -1,2 +1,2 @@\n-x  = 1\n+x = 1\n y = 2\n"
            "@@ -10,3 +10,4 @@\n a = 1\n+b = 2\n c = 3\n@@ -20,2 +20,2 @@\n-z  = 3\n+z = 3\n w = 4\n")

    def report(self, scope):
        sys.path.insert(0, str(PLUGIN / "profiles/python/scripts"))
        from python_lint import format_report

        found = []
        lint = SimpleNamespace(lines={"a.py": scope}, relative=lambda file: file,
                               add=lambda *args, **kwargs: found.append(args[1]))
        self.assertTrue(format_report(lint, self.DIFF))
        return found

    def test_only_ruff_changed_lines_in_the_task_scope_are_reported(self):
        self.assertEqual(self.report(None), [1])
        self.assertEqual(self.report({20, 21}), [20])
        self.assertEqual(self.report({11}), [11])
        self.assertEqual(self.report({5, 6}), [])

    def test_a_replaced_block_is_not_attributed_to_the_next_unchanged_line(self):
        self.assertEqual(self.report({2}), [])
        self.assertEqual(self.report({21}), [])




if __name__ == "__main__":
    unittest.main()
