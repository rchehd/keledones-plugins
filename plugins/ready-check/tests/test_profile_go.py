import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
VALIDATOR = importlib.util.spec_from_file_location("ready_check_package_go", PLUGIN / "scripts/validate-package.py")
package = importlib.util.module_from_spec(VALIDATOR)
VALIDATOR.loader.exec_module(package)
GO = '''#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
mode = os.environ.get("FAKE_GO", "ok")
if args[:1] == ["version"]:
    print("go version go1.26.5 linux/amd64")
    sys.exit(0)
if args[:1] == ["env"]:
    print({"GOROOT": os.environ["FAKE_GOROOT"], "GOPATH": os.environ["FAKE_GOPATH"], "GOBIN": ""}[args[1]])
    sys.exit(0)
if args[:1] == ["vet"]:
    open(os.environ["FAKE_LOG"], "a").write("vet " + " ".join(args[1:]) + "\\n")
    if mode == "vet":
        sys.stderr.write("# example.com/notes\\n./app.go:3:2: fmt.Printf format %d has arg x of wrong type string\\n./app.go:1:1: old finding\\n")
        sys.exit(1)
    if mode == "typeerror":
        sys.stderr.write("# example.com/notes\\n# [example.com/notes]\\nvet: ./other.go:9:1: undefined: helper\\n")
        sys.exit(1)
    if mode == "garbage":
        sys.stderr.write("go: downloading example.com/x v1.0.0\\n")
        sys.exit(1)
    sys.exit(0)
if args[:1] == ["build"]:
    open(os.environ["FAKE_LOG"], "a").write("build " + " ".join(args[1:]) + "\\n")
    if mode == "build":
        sys.stderr.write("# example.com/notes\\n./other.go:9:1: undefined: helper\\n")
        sys.exit(1)
    sys.exit(0)
sys.exit(3)
'''
GOFMT = '''#!/usr/bin/env python3
import os, sys
if os.environ.get("FAKE_GOFMT") == "syntax":
    sys.stderr.write(sys.argv[2] + ":2:8: expected ')', found 'EOF'\\n")
    sys.exit(2)
if os.environ.get("FAKE_GOFMT") == "clean":
    sys.exit(0)
name = sys.argv[2]
print("diff " + name + ".orig " + name + "\\n--- " + name + ".orig\\n+++ " + name + "\\n@@ -1,3 +1,3 @@\\n package main\\n \\n-func a() { x:=1 }\\n+func a() { x := 1 }")
sys.exit(1)
'''
GOLANGCI = '''#!/usr/bin/env python3
import json, os, sys
if "--version" in sys.argv:
    print("golangci-lint has version " + os.environ.get("FAKE_GOLANGCI_VERSION", "2.15.0") + " built with go1.26.5")
    sys.exit(0)
open(os.environ["FAKE_LOG"], "a").write("golangci " + " ".join(sys.argv[1:]) + "\\n")
root = os.getcwd()
issues = [
    {"FromLinter": "gosec", "Text": "G202: SQL string concatenation", "Severity": "medium", "Pos": {"Filename": root + "/app.go", "Line": 3, "Column": 1}},
    {"FromLinter": "errcheck", "Text": "Error return value is not checked", "Severity": "", "Pos": {"Filename": root + "/app.go", "Line": 1, "Column": 1}},
    {"FromLinter": "staticcheck", "Text": "SA4006: unused value", "Severity": "warning", "Pos": {"Filename": root + "/app.go", "Line": 3, "Column": 5}}]
if os.environ.get("FAKE_GOLANGCI") == "typecheck":
    issues = [{"FromLinter": "typecheck", "Text": ": # example.com/notes\\n./other.go:9:1: undefined: helper", "Severity": "", "Pos": {"Filename": root + "/app.go", "Line": 1, "Column": 0}}]
if os.environ.get("FAKE_GOLANGCI") == "broken":
    sys.stderr.write("Error: can't load config\\n")
    sys.exit(3)
print(json.dumps({"Issues": issues, "Report": {}}))
sys.exit(1)
'''
GOVULNCHECK = '''#!/usr/bin/env python3
import json, os, sys
if "--version" in sys.argv:
    print("Go: go1.26.5\\nScanner: govulncheck@v1.9.0\\nDB: https://vuln.go.dev")
    sys.exit(0)
if os.environ.get("FAKE_VULN") == "network":
    sys.stderr.write("govulncheck: fetching vulnerabilities: Get https://vuln.go.dev/index/db.json: dial tcp: lookup vuln.go.dev: no such host\\n")
    sys.exit(1)
out = [{"config": {"scanner_name": "govulncheck"}},
       {"osv": {"id": "GO-2099-0001", "summary": "Request smuggling in example.com/lib"}},
       {"osv": {"id": "GO-2099-0002", "summary": "Not called"}},
       {"finding": {"osv": "GO-2099-0001", "fixed_version": "v1.2.4", "trace": [
           {"module": "example.com/lib", "version": "v1.2.3", "package": "example.com/lib", "function": "Parse"},
           {"module": "example.com/notes", "package": "example.com/notes", "function": "main", "position": {"filename": "app.go", "line": 3}}]}},
       {"finding": {"osv": "GO-2099-0002", "fixed_version": "v2.0.0", "trace": [{"module": "example.com/other", "version": "v1.0.0"}]}}]
for item in out:
    print(json.dumps(item, indent=1))
sys.exit(0)
'''
CHANGED = "package main\n\nfunc a() { x:=1 }\n"


class DetectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if isinstance(data, dict) else data)

    def test_go_module_at_the_root(self):
        self.write("go.mod", "module example.com/notes\n\ngo 1.26\n")
        found = detect.detect(self.root)
        self.assertEqual((found["profile"], found["name"], found["application"], found["runner"]), ("go", "Go", ".", "local"))

    def test_stray_go_mod_in_a_subfolder_does_not_change_the_root_profile(self):
        self.write("requirements.txt", "Django==5.2.1\n")
        self.write("tools/gen/go.mod", "module example.com/gen\n")
        self.assertEqual(detect.detect(self.root)["profile"], "python")
        self.write("composer.json", {"require": {"laravel/framework": "^12.0"}})
        self.write("artisan", "#!/usr/bin/env php\n")
        self.assertEqual(detect.detect(self.root)["profile"], "laravel")

    def test_framework_profiles_win_over_a_root_go_mod(self):
        self.write("go.mod", "module example.com/notes\n")
        self.write("composer.json", {"require": {"laravel/framework": "^12.0"}})
        self.assertEqual(detect.detect(self.root)["profile"], "laravel")
        self.write("composer.json", {"require": {"symfony/framework-bundle": "^7.4"}})
        self.assertEqual(detect.detect(self.root)["profile"], "symfony")

    def test_go_wins_over_a_stray_python_file(self):
        self.write("go.mod", "module example.com/notes\n")
        self.write("requirements.txt", "mkdocs\n")
        self.assertEqual(detect.detect(self.root)["profile"], "go")


class SpecTest(unittest.TestCase):
    def setUp(self):
        self.spec = load_spec("go")

    def test_runner_defaults_choose_app_service_and_root(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            for name in ("LINT_RUNNER", "LINT_SERVICE", "LINT_CONTAINER_ROOT"):
                os.environ.pop(name, None)
            project = Path(folder)
            (project / "compose.yaml").write_text("services:\n  db:\n    image: postgres\n  app:\n    build: .\n")
            runner = Runner(project, {}, self.spec.runner)
            self.assertEqual((runner.name, runner.service, runner.root), ("compose", "app", "/app"))

    def test_every_profile_check_is_implemented(self):
        profile = json.loads((PLUGIN / "profiles/go/profile.json").read_text())
        known = applicable(["main.go", "go.mod", "static/app.js"], self.spec)
        self.assertEqual({c["id"] for c in profile["checks"]} - set(known), set())
        self.assertEqual({c["id"] for c in profile["checks"] if c["required"]},
                         {"gofmt", "vet", "golangci", "build", "debug", "diff", "js"})

    def test_checks_apply_only_to_their_inputs(self):
        def status(*files):
            known = applicable(list(files), self.spec)
            return {k for k in ("gofmt", "vet", "golangci", "build", "govulncheck") if known[k]}

        self.assertFalse(status("README.md"))
        self.assertEqual(status("internal/store/store.go"), {"gofmt", "vet", "golangci", "build", "govulncheck"})
        self.assertEqual(status("go.sum"), {"build", "govulncheck"})

    def test_debug_matches_leftovers_in_app_code_only(self):
        def hit(file, text):
            return bool(self.spec.debug_match(file, text))

        for text in ("spew.Dump(q)", "\tspew.Printf(\"%v\", q)", "pp.Println(x)", "pp.Print(x)", "log.Printf(\"DEBUG q=%s\", q)",
                     "fmt.Println(\"DEBUG\", q)", "fmt.Printf(\"DEBUG %v\", q)", "println(q)"):
            self.assertTrue(hit("app/search.go", text), text)

        for text in ("log.Printf(\"listening on %s\", addr)", "fmt.Println(\"done\")", "fmt.Sprintln(x)", "s.println(x)", "// spew.Dump(x)",
                     "mypp.Println(x)", "log.Println(\"started\")"):
            self.assertFalse(hit("app/search.go", text), text)
        self.assertFalse(hit("app/search_test.go", "println(q)"))
        self.assertFalse(hit("app/search_test.go", "spew.Dump(q)"))
        self.assertTrue(hit("static/app.js", "console.log(x)"))

    def test_generated_paths_are_not_linted(self):
        files = ["main.go", "vendor/x/x.go", "testdata/in.go", "node_modules/y/z.js", "internal/testdata/a.go"]
        self.assertEqual(lint_files(files, self.spec.core_prefixes, self.spec), ["main.go"])

    def test_compatibility_requires_the_pinned_minimum_go(self):
        class Fake:
            def __init__(self, text, status=0):
                self.text, self.status = text, status

            def exec(self, argv, timeout=15):
                return self.status, self.text.encode(), b""

        self.assertEqual(self.spec.compatibility(Fake("go version go1.26.5 linux/amd64"))["go"], "1.26.5")

        with self.assertRaisesRegex(ValueError, "need runner Go 1.26.0"):
            self.spec.compatibility(Fake("go version go1.24.2 linux/amd64"))

        with self.assertRaisesRegex(ValueError, "Go is missing"):
            self.spec.compatibility(Fake("", 127))


class ValidatorTest(unittest.TestCase):
    def tools(self, **changes):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name).resolve()
        source = PLUGIN / "profiles/go/tools"
        tools = root / "tools"
        shutil.copytree(source, tools)
        manifest = json.loads((tools / "tools.json").read_text())

        for name, version in changes.items():
            manifest["tools"][name]["version"] = version
        (tools / "tools.json").write_text(json.dumps(manifest))
        return root, tools

    def test_shipped_tools_are_pinned(self):
        root, tools = self.tools()
        package.go_tools(root, tools, package.PROFILE_TOOLS["go"])

    def test_floating_versions_are_rejected(self):
        for version in ("latest", "v2", "v2.15", "master"):
            root, tools = self.tools(**{"golangci-lint": version})

            with self.assertRaisesRegex(ValueError, "exact version"):
                package.go_tools(root, tools, package.PROFILE_TOOLS["go"])

    def test_default_configuration_must_exist(self):
        root, tools = self.tools()
        (tools / "golangci.yml").unlink()

        with self.assertRaisesRegex(ValueError, "Missing resource"):
            package.go_tools(root, tools, package.PROFILE_TOOLS["go"])

    def test_shipped_default_enables_the_required_linters(self):
        text = (PLUGIN / "profiles/go/tools/golangci.yml").read_text()

        for linter in ("staticcheck", "errcheck", "gosec", "govet", "ineffassign", "unused"):
            self.assertIn("- " + linter, text)


class GofmtOutputTest(unittest.TestCase):
    def test_windows_paths_and_line_endings_in_gofmt_output(self):
        sys.path.insert(0, str(PLUGIN / "profiles/go/scripts"))
        from go_lint import gofmt_report

        file = r"C:\Users\Test User\project\app.go"
        lint = Mock()
        self.assertTrue(gofmt_report(lint, f"{file}:2:8: expected ')'\r\n"))
        lint.add.assert_called_once_with(file, "2", "expected ')'", "error", "gofmt")

        lint.reset_mock()
        lint.lines, lint.relative = {file: None}, lambda name: name
        diff = f"--- {file}.orig\r\n+++ {file}\r\n@@ -2 +2 @@\r\n-x:=1\r\n+x := 1\r\n"
        self.assertTrue(gofmt_report(lint, diff))
        lint.add.assert_called_once_with(file, 2, "File is not formatted as gofmt would write it", "error", "gofmt")

    def test_gofmt_diff_is_reported_only_inside_the_task_lines(self):
        sys.path.insert(0, str(PLUGIN / "profiles/go/scripts"))
        from go_lint import gofmt_report

        diff = "--- a.go.orig\n+++ a.go\n@@ -2 +2 @@\n-x:=1\n+x := 1\n@@ -9,2 +9,3 @@\n a\n+b\n c\n"

        def found(scope):
            lint = Mock(lines={"a.go": scope}, relative=lambda name: name)
            gofmt_report(lint, diff)
            return [call.args[1] for call in lint.add.call_args_list]

        self.assertEqual(found(None), [2])
        self.assertEqual(found({9, 10}), [9])
        self.assertEqual(found({10}), [10])
        self.assertEqual(found({5}), [])


@unittest.skipUnless(shutil.which("git"), "Git is required")
class FakeToolsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.bin = self.root / "bin"
        self.log = self.root / "calls.log"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("LINT_", "READY_CHECK_", "FAKE_"))}
        self.env.update(LINT_RUNNER="local", READY_CHECK_DATA_DIR=str(self.root / "data"), FAKE_LOG=str(self.log),
                        FAKE_GOROOT=str(self.root / "goroot"), FAKE_GOPATH=str(self.root / "gopath"),
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"])
        self.go = write_fake_command(self.bin / "go", GO)
        self.gofmt = write_fake_command(self.root / "goroot/bin/gofmt", GOFMT)
        write_fake_command(self.bin / "golangci-lint", GOLANGCI)
        write_fake_command(self.bin / "govulncheck", GOVULNCHECK)
        self.write("go.mod", "module example.com/notes\n\ngo 1.26\n")
        self.write("app.go", "package main\n")
        self.write(".golangci.yml", 'version: "2"\n')
        self.write("README.md", "# App\n")
        self.git("init", "-b", "main")
        self.git("add", ".")
        self.git("-c", "user.name=F", "-c", "user.email=f@example.invalid", "commit", "-m", "Fixture")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, check=True).stdout

    def write(self, name, content):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def static(self, **modes):
        env = dict(self.env, **modes)
        process = subprocess.run([sys.executable, "-B", str(CHECK), "static", "--profile", "go", "--project", str(self.project),
                                  "--base", "main"], env=env, capture_output=True, text=True, encoding="utf-8")
        data = json.loads(process.stdout)

        if data.get("evidence_directory"):
            self.addCleanup(shutil.rmtree, data["evidence_directory"], True)
        return {c["id"]: c for c in data["checks"]}

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_gofmt_gives_a_file_level_finding_at_the_first_difference(self):
        self.write("app.go", CHANGED)
        gofmt = self.static()["gofmt"]
        self.assertEqual(gofmt["status"], "FAIL", gofmt)
        self.assertEqual([(f["file"], f["line"], f["source"]) for f in gofmt["findings"]], [("app.go", 3, "gofmt")])
        self.assertEqual(gofmt["tools"][0]["name"], "gofmt")
        self.assertEqual(Path(gofmt["tools"][0]["path"]).resolve(), self.gofmt)

    def test_formatted_and_unparsable_files(self):
        self.write("app.go", CHANGED)
        self.assertEqual(self.static(FAKE_GOFMT="clean")["gofmt"]["status"], "PASS")
        syntax = self.static(FAKE_GOFMT="syntax")["gofmt"]
        self.assertEqual(syntax["status"], "FAIL", syntax)
        self.assertEqual((syntax["findings"][0]["file"], syntax["findings"][0]["line"]), ("app.go", 2))

    def test_vet_is_limited_to_changed_lines_and_runs_on_changed_packages(self):
        self.write("app.go", CHANGED)
        self.write("internal/store/store.go", "package store\n")
        vet = self.static(FAKE_GO="vet")["vet"]
        self.assertEqual(vet["status"], "FAIL", vet)
        self.assertEqual([(f["file"], f["line"], f["source"]) for f in vet["findings"]], [("app.go", 3, "vet")])
        self.assertIn("vet . ./internal/store", self.calls())

    def test_vet_type_errors_fail_on_any_line(self):
        self.write("app.go", CHANGED)
        vet = self.static(FAKE_GO="typeerror")["vet"]
        self.assertEqual(vet["status"], "FAIL", vet)
        self.assertEqual([(f["file"], f["line"]) for f in vet["findings"]], [("other.go", 9)])

    def test_unparsable_vet_output_is_incomplete_not_pass(self):
        self.write("app.go", CHANGED)
        self.assertEqual(self.static(FAKE_GO="garbage")["vet"]["status"], "INCOMPLETE")

    def test_build_failure_fails_with_findings_and_discards_output(self):
        self.write("app.go", CHANGED)
        build = self.static(FAKE_GO="build")["build"]
        self.assertEqual(build["status"], "FAIL", build)
        self.assertEqual([(f["file"], f["line"], f["source"]) for f in build["findings"]], [("other.go", 9, "build")])
        self.assertEqual(self.static()["build"]["status"], "PASS")
        self.assertIn("build -o " + os.devnull + " ./...", self.calls())

    def test_golangci_findings_are_limited_to_changed_lines_with_linter_sources(self):
        self.write("app.go", CHANGED)
        golangci = self.static()["golangci"]
        self.assertEqual(golangci["status"], "FAIL", golangci)
        self.assertEqual([(f["line"], f["severity"], f["source"]) for f in golangci["findings"]],
                         [(3, "error", "gosec"), (3, "warning", "staticcheck")])
        self.assertEqual((golangci["tools"][-1]["name"], golangci["tools"][-1]["source"]), ("golangci-lint", "project"))

    def test_golangci_arguments_report_everything_for_changed_packages(self):
        self.write("app.go", CHANGED)
        self.static()
        call = next(c for c in self.calls() if c.startswith("golangci"))
        for part in ("--output.json.path stdout", "--max-issues-per-linter 0", "--max-same-issues 0", "--path-mode abs"):
            self.assertIn(part, call)
        self.assertTrue(call.endswith(" ."), call)

    def test_project_configuration_wins_over_the_managed_default(self):
        self.write("app.go", CHANGED)
        golangci = self.static()["golangci"]
        self.assertEqual(golangci["tools"][-1]["configuration"]["source"], "project")
        call = next(c for c in self.calls() if c.startswith("golangci"))
        config = call.split("--config ", 1)[1].split(" --path-mode", 1)[0]
        self.assertEqual(Path(config).resolve(), self.project / ".golangci.yml")

    def test_managed_default_configuration_needs_the_installed_bundle(self):
        (self.project / ".golangci.yml").unlink()
        self.write("app.go", CHANGED)
        golangci = self.static()["golangci"]
        self.assertEqual(golangci["status"], "INCOMPLETE", golangci)
        self.assertIn("Managed Go tools are not installed", golangci["reason"])

    def test_v1_binary_runs_only_with_the_project_configuration(self):
        self.write("app.go", CHANGED)
        golangci = self.static(FAKE_GOLANGCI_VERSION="1.64.8")["golangci"]
        self.assertEqual((golangci["tools"][-1]["source"], golangci["tools"][-1]["version"]), ("project", "1.64.8"))

    def test_v1_binary_is_not_paired_with_the_managed_v2_default(self):
        sys.path.insert(0, str(PLUGIN / "profiles/go/scripts"))
        import go_tools

        def versioned(runner, name, path, source, spec=None):
            return dict(name=name, path=path, source=source, version="1.64.8" if source == "project" else "2.15.0")

        with patch.object(go_tools, "project_tool", return_value="golangci-lint"), \
                patch.object(go_tools, "versioned", versioned), patch.object(go_tools, "managed_bundle", return_value="/bundle"):
            runner = SimpleNamespace(name="local")
            self.assertEqual(go_tools.tool(runner, "golangci-lint", None, 2)["source"], "profile")
            self.assertEqual(go_tools.tool(runner, "golangci-lint", None)["source"], "project")

    def test_typecheck_issues_surface_package_compile_errors(self):
        self.write("app.go", CHANGED)
        golangci = self.static(FAKE_GOLANGCI="typecheck")["golangci"]
        self.assertEqual(golangci["status"], "FAIL", golangci)
        self.assertEqual([(f["file"], f["line"], f["source"]) for f in golangci["findings"]], [("other.go", 9, "typecheck")])

    def test_golangci_failure_is_incomplete(self):
        self.write("app.go", CHANGED)
        self.assertEqual(self.static(FAKE_GOLANGCI="broken")["golangci"]["status"], "INCOMPLETE")

    def test_govulncheck_reports_called_vulnerabilities_as_warnings(self):
        self.write("app.go", CHANGED)
        vuln = self.static()["govulncheck"]
        self.assertEqual(vuln["status"], "PASS", vuln)
        self.assertEqual([(f["file"], f["line"], f["severity"], f["source"]) for f in vuln["findings"]], [("app.go", 3, "warning", "GO-2099-0001")])
        self.assertIn("fixed in v1.2.4", vuln["findings"][0]["message"])
        self.assertFalse(vuln["required"])

    def test_govulncheck_network_errors_are_incomplete(self):
        self.write("go.sum", "example.com/x v1.0.0 h1:abc=\n")
        vuln = self.static(FAKE_VULN="network")["govulncheck"]
        self.assertEqual(vuln["status"], "INCOMPLETE", vuln)

    def test_module_files_alone_run_build_and_govulncheck_only(self):
        self.write("go.sum", "example.com/x v1.0.0 h1:abc=\n")
        checks = self.static()

        for name in ("gofmt", "vet", "golangci"):
            self.assertEqual(checks[name]["status"], "N/A", checks[name])

        for name in ("build", "govulncheck"):
            self.assertNotEqual(checks[name]["status"], "N/A", checks[name])

    def test_debug_catches_app_code_and_ignores_tests(self):
        self.write("app.go", "package main\n\nfunc a() {\n\tspew.Dump(1)\n\tprintln(2)\n}\n")
        self.write("app_test.go", "package main\n\nfunc b() { println(3) }\n")
        debug = self.static()["debug"]
        self.assertEqual(debug["status"], "FAIL", debug)
        self.assertEqual(sorted((f["file"], f["line"]) for f in debug["findings"]), [("app.go", 4), ("app.go", 5)])

    def test_missing_go_is_incomplete_not_pass(self):
        self.write("app.go", CHANGED)
        self.go.unlink()
        git = self.root / "git-only/git"
        git_path = shutil.which("git")
        if os.name == "nt":
            write_fake_command(git, '#!/usr/bin/env python3\nimport subprocess, sys\n'
                                    f'sys.exit(subprocess.call([{git_path!r}, *sys.argv[1:]]))\n')
        else:
            git.parent.mkdir()
            git.symlink_to(git_path)
        vet = self.static(PATH=str(self.bin) + os.pathsep + str(git.parent))["vet"]
        self.assertEqual(vet["status"], "INCOMPLETE", vet)

    def test_checks_are_not_applicable_when_inputs_did_not_change(self):
        self.write("README.md", "# Changed\n")
        checks = self.static()

        for name in ("gofmt", "vet", "golangci", "build", "govulncheck"):
            self.assertEqual(checks[name]["status"], "N/A", checks[name])

    def test_project_is_not_written_by_the_checks(self):
        self.write("app.go", CHANGED)
        before = sorted(p.relative_to(self.project).as_posix() for p in self.project.rglob("*") if ".git" not in p.parts)
        self.static()
        after = sorted(p.relative_to(self.project).as_posix() for p in self.project.rglob("*") if ".git" not in p.parts)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
