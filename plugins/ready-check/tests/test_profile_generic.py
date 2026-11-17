import shutil

from helpers import RepoTest


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
                         {"diff": "PASS", "syntax": "PASS", "shell": "PASS"})
        self.assertTrue(result["can_proceed"])

    def test_invalid_shell_python_and_json_block_the_static_gate(self):
        self.write("scripts/task.py", "return 1\n")
        self.write("scripts/task.bash", "#!/usr/bin/env bash\nif true; then\n  echo ready\n")
        self.write("config.json", '{"enabled": }\n')
        result = self.static(code=1)
        findings = {(f["file"], f["source"]) for check in result["checks"] for f in check["findings"]}
        self.assertEqual(findings, {("scripts/task.py", "python"), ("scripts/task.bash", "bash"), ("config.json", "json")})
        self.assertFalse(result["can_proceed"])

    def test_compose_file_alone_leaves_generic_checks_local(self):
        self.write("compose.yml", "services: {}\n")
        self.write("scripts/task.py", "print('ready')\n")
        self.assertEqual(self.static()["runner"], "local")

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
