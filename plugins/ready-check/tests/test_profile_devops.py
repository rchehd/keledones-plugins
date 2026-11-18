import json
import os

from helpers import RepoTest, write_fake_command


class DevOpsTest(RepoTest):
    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def tool(self, name, code):
        write_fake_command(self.root / "bin" / name, "#!/usr/bin/env python3\n" + code)

    def static(self, code=0, action="static", paths=()):
        return self.entry_json(action, "--profile", "devops", "--project", str(self.repo), "--base", "main",
                               "--output", str(self.root / f"{action}.json"),
                               *(f"--path={path}" for path in paths),
                               env={"LINT_RUNNER": "", "COMPOSE_FILE": "",
                                    "PATH": str(self.root / "bin") + os.pathsep + os.environ["PATH"]}, code=code)

    def test_discovery_keeps_application_runner_and_devops_runner_separate(self):
        self.write("composer.json", '{"require":{"drupal/core":"^11"}}')
        self.write("compose.yaml", "services: {}\n")
        self.write("frontend/tsconfig.json", "{}")
        self.write("frontend/.github/workflows/frontend.yml", "jobs: {}\n")
        result = self.entry_json("profiles", "--project", str(self.repo))
        self.assertEqual({(item["profile"], item["application"], item["runner"]) for item in result["profiles"]},
                         {("drupal", ".", "compose"), ("devops", ".", "local"),
                          ("typescript", "frontend", "local"), ("devops", "frontend", "local")})

    def test_compose_checks_ordered_files_and_keeps_env_values_out_of_evidence(self):
        self.write("compose.yaml", "services: {}\n")
        self.write("compose.dev.yaml", "services: {}\n")
        self.write(".ready-check.json", json.dumps({"devops": {"compose_files": ["compose.yaml", "compose.dev.yaml"]}}))
        self.tool("docker", """import sys
if sys.argv[1:] == ['compose', 'version']:
    print('Docker Compose version v2.40.0')
    raise SystemExit(0)
assert sys.argv[1:] == ['compose', '-f', 'compose.yaml', '-f', 'compose.dev.yaml', 'config', '--quiet']
print('expanded secret value', file=sys.stderr)
raise SystemExit(1)
""")
        result = self.static(code=1)
        check = next(check for check in result["checks"] if check["id"] == "compose")
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual((self.root / "static.json").read_text(encoding="utf-8").count("expanded secret value"), 0)
        self.assertNotIn("expanded secret value", (self.root / check["evidence"][0]).read_text(encoding="utf-8"))

    def test_unselected_compose_variant_is_incomplete(self):
        self.write("compose.yaml", "services: {}\n")
        self.write("compose.prod.yaml", "services: {}\n")
        report = self.static(code=2, action="doctor")
        check = next(check for check in report["checks"] if check["id"] == "compose")
        self.assertIn("outside the selected stack", check["reason"])

    def test_actionlint_finding_is_blocking(self):
        self.write(".github/workflows/ci.yml", "jobs: []\n")
        self.write("compose.unselected.yaml", "services: {}\n")
        self.tool("actionlint", """import json, sys
if sys.argv[1:] == ['-version']:
    print('1.7.11')
    raise SystemExit(0)
print(json.dumps([dict(filepath=sys.argv[-1], line=1, message='Expected a mapping', kind='syntax-check')]))
raise SystemExit(1)
""")
        paths = (".github/workflows",)
        doctor = self.static(action="doctor", paths=paths)
        report = self.static(code=1, paths=paths)
        self.assertEqual(doctor["scope"]["snapshot"], report["scope"]["snapshot"])
        self.assertEqual(report["scope"]["outside_scope"], ["compose.unselected.yaml"])
        check = next(check for check in report["checks"] if check["id"] == "actionlint")
        self.assertEqual(check["findings"][0]["message"], "Expected a mapping")
