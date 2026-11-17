import os

from helpers import RepoTest, write_fake_command

PUBSPEC = """name: demo
dependencies:
  flutter:
    sdk: flutter
"""

MOCK_SDK = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if '--version' in args:
    assert '--machine' in args
    print(json.dumps({'frameworkVersion': '3.41.2', 'dartSdkVersion': '3.11.0'}))
elif 'analyze' in args:
    assert '--no-pub' in args
    source = Path('lib/main.dart')
    if 'ANALYZER' in source.read_text(encoding='utf-8'):
        divider = ' - ' if os.name == 'nt' else ' ' + chr(8226) + ' '
        print(divider.join(['error', 'Undefined identifier', 'lib/main.dart:1:5', 'undefined_identifier']))
        raise SystemExit(1)
else:
    assert '--output=none' in args and '--set-exit-if-changed' in args
    source = Path(args[-1])
    if 'FORMAT' in source.read_text(encoding='utf-8'):
        print(f'Changed {source}')
        raise SystemExit(1)
"""


class FlutterTest(RepoTest):
    def write(self, relative, content):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def prepare_package(self):
        self.write("pubspec.yaml", PUBSPEC)
        self.write(".gitignore", ".fvm/\n.dart_tool/\n")
        self.write(".fvmrc", '{"flutter":"3.41.2"}\n')
        self.git("add", ".")
        self.git("commit", "-qm", "Flutter fixtures")
        self.packages = self.write(".dart_tool/package_config.json", '{"configVersion":2,"packages":[]}\n')

        prefix = ".fvm/flutter_sdk/"
        self.write(prefix + "bin/cache/flutter_tools.snapshot", "")
        if os.name == "nt":
            self.write(prefix + "bin/flutter.bat", "@exit /b 99\n")
            self.write(prefix + "packages/flutter_tools/.dart_tool/package_config.json", "{}\n")
        else:
            write_fake_command(self.repo / prefix / "bin/flutter", MOCK_SDK)
        write_fake_command(self.repo / prefix / "bin/cache/dart-sdk/bin/dart", MOCK_SDK)

    def check(self, action, code=0):
        return self.entry_json(action, "--project", str(self.repo), "--profile", "flutter", "--base", "main",
                               "--output", str(self.root / f"{action}.json"), code=code,
                               env={"FLUTTER_ROOT": str(self.root / "wrong-sdk"), "LINT_RUNNER": ""})

    def test_detects_nested_flutter_sdk_and_distinguishes_a_dart_package(self):
        self.write("apps/mobile/pubspec.yaml", PUBSPEC)
        self.write("apps/inline/pubspec.yaml", "dependencies: {flutter: {sdk: 'flutter'}}\n")
        self.write("tools/dart/pubspec.yaml", "name: tools\nenvironment:\n  sdk: ^3.0.0\nflutter:\n  uses-material-design: true\n")
        result = self.entry_json("profiles", "--project", str(self.repo))
        families = {(item["profile"], item["application"]) for item in result["profiles"]}
        self.assertEqual(families, {("flutter", "apps/mobile"), ("flutter", "apps/inline")})

    def test_pinned_sdk_runs_analysis_and_non_writing_formatter(self):
        self.prepare_package()
        source = self.write("lib/main.dart", "void main() {}\n")
        doctor = self.check("doctor")
        report = self.check("static")
        self.assertTrue(report["can_proceed"])
        self.assertEqual(doctor["scope"]["snapshot"], report["scope"]["snapshot"])
        tools = next(check["tools"] for check in report["checks"] if check["id"] == "flutter-analyze")
        self.assertEqual([tool["version"] for tool in tools], ["3.41.2", "3.11.0"])
        self.assertEqual(tools[0]["source"], "project")
        self.assertEqual(source.read_text(encoding="utf-8"), "void main() {}\n")

        source = self.write("lib/main.dart", "ANALYZER FORMAT\n")
        report = self.check("static", code=1)
        findings = {(item["source"], item["file"]) for check in report["checks"] for item in check["findings"]}
        self.assertEqual(findings, {("undefined_identifier", "lib/main.dart"), ("dart-format", "lib/main.dart")})
        self.assertEqual(source.read_text(encoding="utf-8"), "ANALYZER FORMAT\n")

    def test_missing_prerequisite_keeps_analysis_incomplete(self):
        self.prepare_package()
        self.write("lib/main.dart", "void main() {}\n")
        self.packages.unlink()
        report = self.check("static", code=2)
        analysis = next(check for check in report["checks"] if check["id"] == "flutter-analyze")
        self.assertEqual(analysis["status"], "INCOMPLETE")
        self.assertIn("project packages are unavailable", analysis["reason"])

        sdk_bin = self.repo / ".fvm/flutter_sdk/bin"
        (sdk_bin / ("flutter.bat" if os.name == "nt" else "flutter")).unlink()
        doctor = self.check("doctor", code=2)
        formatter = next(check for check in doctor["checks"] if check["id"] == "dart-format")
        self.assertEqual(formatter["status"], "MISSING")
        self.assertIn("pins Flutter with FVM", formatter["reason"])
