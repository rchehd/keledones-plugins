import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
import detect
import hook
from core_main import applicable
from core_runner import Runner
from core_scope import lint_files
from profile_runtime import load_spec

CHECK = PLUGIN / "scripts/check-profile.py"
PINT = '''#!/usr/bin/env python3
import json, sys
if "--version" in sys.argv:
    print("Pint 1.30.4")
    sys.exit(0)
print(json.dumps({"tool": "pint", "result": "fail", "files": [{"path": "app/Foo.php", "fixers": ["no_unused_imports", "braces_position"]}]}))
sys.exit(1)
'''
RECTOR = '''#!/usr/bin/env python3
import json, sys
if "--version" in sys.argv:
    print("Rector 2.8.3")
    sys.exit(0)
print(json.dumps({"totals": {"changed_files": 1, "errors": 0}, "file_diffs": [{"file": "app/Foo.php", "diff": "",
      "applied_rectors": ["RectorLaravel\\\\Rector\\\\FuncCall\\\\HelperFuncCallToFacadeClassRector"]}]}))
sys.exit(2)
'''


class DetectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if isinstance(data, dict) else data)

    def test_laravel_application(self):
        self.write("composer.json", {"require": {"laravel/framework": "^12.0"}})
        self.write("composer.lock", {"packages": [{"name": "laravel/framework", "version": "v12.3.0"}]})
        self.write(".ddev/config.yaml", "name: x\n")
        found = detect.detect(self.root)
        self.assertEqual((found["profile"], found["name"], found["version"], found["runner"]), ("laravel", "Laravel", "12", "ddev"))
        self.assertEqual(hook.describe(found), "Laravel 12, DDEV")

    def test_artisan_alone_and_drupal_stay_distinct(self):
        self.write("artisan", "#!/usr/bin/env php\n")
        self.assertEqual(detect.detect(self.root)["profile"], "laravel")
        self.write("web/core/lib/Drupal.php", "<?php\n")
        self.write("composer.json", {"require": {"drupal/core-recommended": "^11"}})
        (self.root / "artisan").unlink()
        self.assertEqual(detect.detect(self.root)["profile"], "drupal")

    def test_composer_and_package_json_together_pick_the_php_profile(self):
        self.write("composer.json", {"require": {"laravel/framework": "^12.0"}})
        self.write("package.json", {"name": "app", "devDependencies": {"vite": "^6"}})
        self.assertEqual(detect.detect(self.root)["profile"], "laravel")

    def test_two_applications_are_ambiguous(self):
        self.write("a/composer.json", {"require": {"laravel/framework": "^12.0"}})
        self.write("b/composer.json", {"require": {"drupal/core": "^11"}})
        found = detect.detect(self.root)
        self.assertTrue(found["ambiguous"])
        self.assertIsNone(found["profile"])

    def test_unrelated_project_has_no_profile(self):
        self.write("package.json", {"name": "x"})
        self.assertIsNone(detect.detect(self.root)["profile"])


class SpecTest(unittest.TestCase):
    def setUp(self):
        self.spec = load_spec("laravel")

    def test_runner_defaults_choose_sail_service_and_root(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            for name in ("LINT_RUNNER", "LINT_SERVICE", "LINT_CONTAINER_ROOT"):
                os.environ.pop(name, None)
            project = Path(folder)
            (project / "docker-compose.yml").write_text("services:\n  mysql:\n    image: mysql\n  laravel.test:\n    build: .\n")
            runner = Runner(project, {}, self.spec.runner)
            self.assertEqual((runner.name, runner.service, runner.root), ("compose", "laravel.test", "/var/www/html"))

    def test_every_profile_check_is_implemented(self):
        profile = json.loads((PLUGIN / "profiles/laravel/profile.json").read_text())
        known = applicable(["app/Foo.php", "composer.lock", "resources/js/app.js"], self.spec)
        self.assertEqual({c["id"] for c in profile["checks"]} - set(known), set())

    def test_debug_pattern(self):
        pattern = self.spec.debug_pattern

        for line in ("dd($note);", "    dump($x);", "ray($x)->red();", "var_dump($a);", "print_r($a);", "{{ dd($note) }}"):
            self.assertTrue(pattern.search(line), line)

        for line in ("$adder(1);", "adder($x);", "$this->added($x);", "print_r($a, true);", "// no debug here"):
            self.assertFalse(pattern.search(line), line)

    def test_blade_and_generated_paths_are_not_linted_as_php(self):
        from php_runtime import is_php
        self.assertTrue(is_php(self.spec, "app/Foo.php"))
        self.assertFalse(is_php(self.spec, "resources/views/a.blade.php"))
        files = ["app/A.php", "storage/logs/x.php", "bootstrap/cache/services.php", "public/build/app.js", "vendor/x/y.php"]
        self.assertEqual(lint_files(files, self.spec.core_prefixes, self.spec), ["app/A.php"])


@unittest.skipUnless(shutil.which("php") and shutil.which("git"), "PHP and Git are required")
class FakeToolsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("LINT_", "READY_CHECK_TEST_"))}
        self.env.update(LINT_RUNNER="local", READY_CHECK_DATA_DIR=str(self.root / "data"))
        self.write("composer.json", '{"require":{"laravel/framework":"^12.0"}}\n')
        self.write(".gitignore", "vendor/\n")
        self.write("app/Foo.php", "<?php\n\nclass Foo\n{\n}\n")
        self.git("init", "-b", "main")
        self.git("add", ".")
        self.git("-c", "user.name=F", "-c", "user.email=f@example.invalid", "commit", "-m", "Fixture")
        self.write("app/Foo.php", "<?php\n\nclass Foo\n{\n    public function a() { return 1; }\n}\n")

        for name, body in (("pint", PINT), ("rector", RECTOR)):
            self.write("vendor/bin/" + name, body).chmod(0o755)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, check=True).stdout

    def write(self, name, content):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def static(self):
        process = subprocess.run([sys.executable, "-B", str(CHECK), "static", "--profile", "laravel", "--project", str(self.project),
                                  "--base", "main"], env=self.env, capture_output=True, text=True, encoding="utf-8")
        data = json.loads(process.stdout)

        if data.get("evidence_directory"):
            self.addCleanup(shutil.rmtree, data["evidence_directory"], True)
        return {c["id"]: c for c in data["checks"]}

    def test_pint_and_rector_results_are_parsed(self):
        checks = self.static()
        pint, rector = checks["pint"], checks["rector"]
        self.assertEqual(pint["status"], "FAIL", pint)
        self.assertEqual((pint["findings"][0]["file"], pint["findings"][0]["line"], pint["findings"][0]["source"]), ("app/Foo.php", 0, "pint"))
        self.assertIn("no_unused_imports", pint["findings"][0]["message"])
        self.assertEqual(pint["tools"][0]["source"], "project")
        self.assertEqual(rector["status"], "PASS", rector)
        self.assertEqual((rector["findings"][0]["severity"], rector["findings"][0]["file"]), ("warning", "app/Foo.php"))
        self.assertIn("HelperFuncCallToFacadeClassRector", rector["findings"][0]["message"])

    def test_unparsable_pint_output_is_incomplete(self):
        self.write("vendor/bin/pint", '#!/bin/sh\n[ "$1" = "--version" ] && echo "Pint 1.30.4" && exit 0\necho nonsense\n').chmod(0o755)
        self.assertEqual(self.static()["pint"]["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
