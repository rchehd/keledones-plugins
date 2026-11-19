import os
import shutil

from helpers import RepoTest, write_fake_command


class GenericTest(RepoTest):
    def write(self, name, content):
        file = self.repo / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")

    def static(self, code=0):
        result = self.entry_json("static", "--profile", "generic", "--project", str(self.repo), "--base", "main", code=code)
        if "evidence_directory" in result:
            self.addCleanup(shutil.rmtree, result["evidence_directory"], ignore_errors=True)
        return result

    def test_setup_falls_back_without_installing_profile_tools(self):
        self.write("scripts/task.py", "print('ready')\n")
        setup = self.entry_json("setup", "--project", str(self.repo), "--component", "profile")
        self.assertEqual(setup["status"], "PASS")
        self.assertEqual(setup["components"][0]["component"], "generic")
        self.assertFalse(self.data.exists())

    def test_valid_scripts_are_parsed_without_execution(self):
        self.write("scripts/task.py", "raise RuntimeError('script was executed')\n")
        self.write("scripts/task.sh", "#!/bin/sh\nexit 1\n")
        self.write("config.json", '{"enabled": true}\n')
        self.write(".vscode/settings.json", '{ // editor JSONC\n"editor.tabSize": 2,\n}\n')
        result = self.static()
        self.assertEqual({c["id"]: c["status"] for c in result["checks"]},
                         {"diff": "PASS", "syntax": "PASS", "shell": "PASS", "yaml": "N/A"})
        self.assertTrue(result["can_proceed"])

    def test_invalid_shell_python_and_json_block_the_static_gate(self):
        self.write("scripts/task.py", "return 1\n")
        self.write("scripts/task.bash", "#!/usr/bin/env bash\nif true; then\n  echo ready\n")
        self.write("config.json", '{"enabled": }\n')
        result = self.static(code=1)
        findings = {(f["file"], f["source"]) for check in result["checks"] for f in check["findings"]}
        self.assertEqual(findings, {("scripts/task.py", "python"), ("scripts/task.bash", "bash"), ("config.json", "json")})
        self.assertFalse(result["can_proceed"])

    def test_sh_files_use_bash_when_declared(self):
        self.write("scripts/direct.sh", "#!/bin/bash\nitems=(one two)\n")
        self.write("scripts/via-env.sh", "#!/usr/bin/env bash\nitems=(one two)\n")
        result = self.static()
        check = next(check for check in result["checks"] if check["id"] == "shell")
        self.assertEqual(check["status"], "PASS")
        self.assertTrue(result["can_proceed"])

    def test_shell_bom_reports_the_header_instead_of_sh_syntax_errors(self):
        self.write("scripts/task.sh", "\ufeff#!/bin/bash\nitems=(one two)\n")
        result = self.static(code=1)
        check = next(check for check in result["checks"] if check["id"] == "shell")
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(len(check["findings"]), 1)
        finding = check["findings"][0]
        self.assertEqual((finding["file"], finding["line"], finding["source"]), ("scripts/task.sh", 1, "shebang"))
        self.assertIn("UTF-8 BOM", finding["message"])

    def test_compose_file_alone_leaves_generic_checks_local(self):
        self.write("compose.yml", "services: {}\n")
        self.write("scripts/task.py", "print('ready')\n")
        bin_dir = self.root / "bin"
        write_fake_command(bin_dir / "yamllint", "#!/usr/bin/env python3\nprint('yamllint 1.38.0')\n")
        doctor = self.entry_json("doctor", "--profile", "generic", "--project", str(self.repo), "--base", "main",
                                 env={"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        self.assertEqual(doctor["runner"], "local")

    def test_helm_templates_are_not_sent_to_yamllint(self):
        self.write("chart/Chart.yaml", "name: demo\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Add chart")
        self.write("chart/templates/service.yaml", "{{- if .Values.enabled }}\n")
        check = next(check for check in self.static()["checks"] if check["id"] == "yaml")
        self.assertEqual(check["status"], "N/A")
        self.assertIn("renderer", check["reason"])

    def test_yaml_uses_the_closest_config_and_surfaces_syntax_errors(self):
        bin_dir = self.root / "bin"
        write_fake_command(bin_dir / "yamllint", """#!/usr/bin/env python3
import sys
if '--version' in sys.argv:
    print('yamllint 1.38.0')
    raise SystemExit(0)
assert sys.argv[1:6] == ['-f', 'parsable', '-c', 'conf/.yamllint', '--']
print(sys.argv[-1] + ':1:12: [error] syntax error: expected a closing bracket (syntax)')
raise SystemExit(1)
""")
        self.write("conf/.yamllint", "{rules: {}}\n")
        self.write("conf/settings.yaml", "enabled: [true\n")
        report = self.entry_json("static", "--profile", "generic", "--project", str(self.repo), "--base", "main",
                                 "--output", str(self.root / "yaml.json"), code=1,
                                 env={"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        check = next(check for check in report["checks"] if check["id"] == "yaml")
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["findings"][0]["file"], "conf/settings.yaml")

    def test_mixed_languages_stay_in_scope(self):
        self.write("worker.rs", "fn main() {}\n")
        self.write("server.ts", "export const port = 3000;  \n")
        self.write("scripts/task.py", "print('ready')\n")
        self.write(".github/workflows/ci.yml", "name: test\n")
        result = self.static(code=1)
        self.assertEqual(set(result["scope"]["files"]),
                         {"worker.rs", "server.ts", "scripts/task.py", ".github/workflows/ci.yml"})
        checks = {c["id"]: c for c in result["checks"]}
        self.assertEqual(checks["syntax"]["status"], "PASS")
        self.assertEqual(checks["shell"]["status"], "N/A")
        self.assertEqual(checks["diff"]["findings"][0]["file"], "server.ts")
