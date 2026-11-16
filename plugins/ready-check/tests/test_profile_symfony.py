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
from core_main import applicable
from core_runner import Runner
from core_scope import lint_files
from profile_runtime import load_spec

CHECK = PLUGIN / "scripts/check-profile.py"
CSFIXER = '''#!/usr/bin/env python3
import json, sys
if "--version" in sys.argv:
    print("PHP CS Fixer 3.95.27 Adalbertus")
    sys.exit(0)
diff = "--- a/src/Foo.php\\n+++ b/src/Foo.php\\n@@ -3,5 +3,5 @@\\n class Foo\\n {\\n-    public function a() {return 1;}\\n+    public function a() { return 1; }\\n }\\n"
print(json.dumps({"files": [{"name": "src/Foo.php", "appliedFixers": ["braces_position"], "diff": diff}]}))
sys.exit(8)
'''
CONSOLE = '''<?php
$argv = $_SERVER['argv'];
$mode = getenv('FAKE_CONSOLE') ?: 'ok';

if ($mode === 'boot') {
    fwrite(STDERR, "In FileLoader.php line 190:\\n\\n  [Symfony\\\\Component\\\\Config\\\\Exception\\\\LoaderLoadException]\\n  broken\\n");
    exit(1);
}
$command = $argv[1];

if ($command === 'lint:container') {
    if ($mode === 'invalid') {
        fwrite(STDERR, "\\nIn Pass.php line 1:\\n\\n  [Symfony\\\\Component\\\\DependencyInjection\\\\Exception\\\\RuntimeException]  \\n  Invalid service \\"App\\\\X\\": no ctor.        \\n  more  \\n\\n\\nException trace:\\n");
        exit(1);
    }
    echo " [OK] The container was linted successfully\\n";
    exit(0);
}
$files = array_values(array_filter(array_slice($argv, 2), fn ($a) => $a[0] !== '-'));
$rows = [];

foreach ($files as $file) {
    $row = ['file' => $file, 'valid' => $mode !== 'invalid'];

    if ($mode === 'invalid') {
        $row['line'] = 2;
        $row['message'] = 'Broken in ' . $command;
    }
    $rows[] = $row;
}
echo json_encode($rows);
exit($mode === 'invalid' ? 1 : 0);
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

    def test_symfony_application(self):
        self.write("composer.json", {"require": {"symfony/framework-bundle": "^7.4"}})
        self.write("composer.lock", {"packages": [{"name": "symfony/framework-bundle", "version": "v7.4.3"}]})
        found = detect.detect(self.root)
        self.assertEqual((found["profile"], found["name"], found["version"], found["runner"]), ("symfony", "Symfony", "7", "local"))

    def test_console_or_lock_file_alone_is_enough(self):
        self.write("bin/console", "#!/usr/bin/env php\n")
        self.assertEqual(detect.detect(self.root)["profile"], "symfony")

    def test_laravel_and_drupal_stay_distinct(self):
        self.write("composer.json", {"require": {"laravel/framework": "^12.0", "symfony/framework-bundle": "^7.4"}})
        self.write("bin/console", "#!/usr/bin/env php\n")
        self.assertEqual(detect.detect(self.root)["profile"], "laravel")
        self.write("composer.json", {"require": {"drupal/core-recommended": "^11", "symfony/framework-bundle": "^7.4"}})
        self.write("web/core/lib/Drupal.php", "<?php\n")
        self.assertEqual(detect.detect(self.root)["profile"], "drupal")


class SpecTest(unittest.TestCase):
    def setUp(self):
        self.spec = load_spec("symfony")

    def test_runner_defaults_choose_php_service_and_app_root(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            for name in ("LINT_RUNNER", "LINT_SERVICE", "LINT_CONTAINER_ROOT"):
                os.environ.pop(name, None)
            project = Path(folder)
            (project / "compose.yaml").write_text("services:\n  database:\n    image: postgres\n  php:\n    build: .\n")
            runner = Runner(project, {}, self.spec.runner)
            self.assertEqual((runner.name, runner.service, runner.root), ("compose", "php", "/app"))

    def test_every_profile_check_is_implemented(self):
        profile = json.loads((PLUGIN / "profiles/symfony/profile.json").read_text())
        known = applicable(["src/Foo.php", "composer.lock", "assets/app.js", "config/services.yaml"], self.spec)
        self.assertEqual({c["id"] for c in profile["checks"]} - set(known), set())

    def test_console_checks_apply_only_to_their_inputs(self):
        def status(*files):
            known = applicable(list(files), self.spec)
            return {name: known[name] for name in ("container", "yaml", "twig", "xliff", "schema")}

        self.assertEqual(status("README.md"), dict(container=False, yaml=False, twig=False, xliff=False, schema=False))
        self.assertEqual(status("templates/a.html.twig"), dict(container=False, yaml=False, twig=True, xliff=False, schema=False))
        self.assertEqual(status("translations/a.en.xlf"), dict(container=False, yaml=False, twig=False, xliff=True, schema=False))
        self.assertEqual(status("config/services.yaml"), dict(container=True, yaml=True, twig=False, xliff=False, schema=False))
        self.assertEqual(status("src/Entity/Foo.php"), dict(container=True, yaml=False, twig=False, xliff=False, schema=True))
        self.assertEqual(status("src/Service/Foo.php")["schema"], False)

    def test_debug_pattern(self):
        pattern = self.spec.debug_pattern

        for line in ("dump($note);", "    dd($x);", "var_dump($a);", "print_r($a);", "{{ dump(item) }}"):
            self.assertTrue(pattern.search(line), line)

        for line in ("$adder(1);", "$this->added($x);", "print_r($a, true);", "// no debug here"):
            self.assertFalse(pattern.search(line), line)

    def test_generated_paths_are_not_linted(self):
        files = ["src/A.php", "var/cache/x.php", "public/build/app.js", "public/bundles/x.js", "vendor/x/y.php"]
        self.assertEqual(lint_files(files, self.spec.core_prefixes, self.spec), ["src/A.php"])


@unittest.skipUnless(shutil.which("php") and shutil.which("git"), "PHP and Git are required")
class FakeToolsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("LINT_", "READY_CHECK_TEST_", "FAKE_"))}
        self.env.update(LINT_RUNNER="local", READY_CHECK_DATA_DIR=str(self.root / "data"))
        self.write("composer.json", '{"require":{"symfony/framework-bundle":"^7.4"}}\n')
        self.write(".gitignore", "vendor/\n")
        self.write("src/Foo.php", "<?php\n\nclass Foo\n{\n}\n")
        self.write("config/services.yaml", "services: {}\n")
        self.write("templates/a.html.twig", "<p>a</p>\n")
        self.write("README.md", "# App\n")
        self.git("init", "-b", "main")
        self.git("add", ".")
        self.git("-c", "user.name=F", "-c", "user.email=f@example.invalid", "commit", "-m", "Fixture")
        self.write("vendor/bin/php-cs-fixer", CSFIXER).chmod(0o755)
        self.write("bin/console", CONSOLE)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.project, capture_output=True, text=True, check=True).stdout

    def write(self, name, content):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def change(self, *names):
        for name in names:
            self.write(name, "<?php\n\nclass Foo\n{\n    public function a() { return 1; }\n}\n" if name.endswith(".php")
                       else "changed: true\n" if name.endswith(".yaml") else "<p>b</p>\n")

    def static(self, mode=None):
        env = dict(self.env, **({"FAKE_CONSOLE": mode} if mode else {}))
        process = subprocess.run([sys.executable, "-B", str(CHECK), "static", "--profile", "symfony", "--project", str(self.project),
                                  "--base", "main"], env=env, capture_output=True, text=True, encoding="utf-8")
        data = json.loads(process.stdout)

        if data.get("evidence_directory"):
            self.addCleanup(shutil.rmtree, data["evidence_directory"], True)
        return {c["id"]: c for c in data["checks"]}

    def test_php_cs_fixer_json_is_parsed(self):
        self.change("src/Foo.php")
        fixer = self.static()["csfixer"]
        self.assertEqual(fixer["status"], "FAIL", fixer)
        finding = fixer["findings"][0]
        self.assertEqual((finding["file"], finding["line"], finding["source"]), ("src/Foo.php", 5, "csfixer"))
        self.assertIn("braces_position", finding["message"])
        self.assertEqual(fixer["tools"][0]["source"], "project")

    def test_unparsable_php_cs_fixer_output_is_incomplete(self):
        self.write("vendor/bin/php-cs-fixer", '#!/bin/sh\n[ "$1" = "--version" ] && echo "PHP CS Fixer 3.95.27" && exit 0\necho nonsense\n').chmod(0o755)
        self.change("src/Foo.php")
        self.assertEqual(self.static()["csfixer"]["status"], "INCOMPLETE")

    def test_console_lints_pass_on_valid_input(self):
        self.change("src/Foo.php", "config/services.yaml", "templates/a.html.twig")
        checks = self.static()

        for name in ("container", "yaml", "twig"):
            self.assertEqual(checks[name]["status"], "PASS", checks[name])

    def test_console_lint_failures_become_findings(self):
        self.change("src/Foo.php", "config/services.yaml", "templates/a.html.twig")
        checks = self.static("invalid")
        self.assertEqual(checks["twig"]["status"], "FAIL", checks["twig"])
        self.assertEqual((checks["twig"]["findings"][0]["file"], checks["twig"]["findings"][0]["line"]), ("templates/a.html.twig", 2))
        self.assertIn("lint:twig", checks["twig"]["findings"][0]["message"])
        self.assertEqual(checks["yaml"]["status"], "FAIL")
        self.assertEqual(checks["container"]["status"], "FAIL", checks["container"])
        self.assertEqual(checks["container"]["findings"][0]["message"], 'Invalid service "App\\X": no ctor. more')

    def test_console_that_cannot_boot_is_incomplete_not_pass(self):
        self.change("src/Foo.php", "config/services.yaml", "templates/a.html.twig")
        checks = self.static("boot")

        for name in ("container", "yaml", "twig"):
            self.assertEqual(checks[name]["status"], "INCOMPLETE", checks[name])

    def test_checks_are_not_applicable_when_inputs_did_not_change(self):
        self.write("README.md", "# Changed\n")
        checks = self.static()

        for name in ("csfixer", "container", "yaml", "twig", "xliff", "schema"):
            self.assertEqual(checks[name]["status"], "N/A", checks[name])

    def test_schema_is_not_applicable_without_doctrine(self):
        self.change("src/Entity/Foo.php")
        self.assertEqual(self.static()["schema"]["status"], "N/A")


if __name__ == "__main__":
    unittest.main()
