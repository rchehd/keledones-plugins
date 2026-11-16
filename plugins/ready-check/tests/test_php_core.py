import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parent.parent
SHARED = PLUGIN / "profiles/_shared"
sys.path.insert(0, str(SHARED / "core"))
from core_runner import Runner

COMPOSE = """name: demo
services:
  web:
    image: nginx
    environment:
      php: ignored
  laravel.test:
    image: sail
  php:
    image: php
volumes:
  data: {}
"""


class RunnerSelectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-php-core.")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.defaults = dict(services=("laravel.test", "php"), root="/app")

    def runner(self, config=None, defaults=None, **env):
        with patch.dict(os.environ, dict(env, LINT_RUNNER="compose"), clear=True):
            return Runner(self.project, config or {}, defaults or self.defaults)

    def compose(self, text):
        (self.project / "compose.yaml").write_text(text)

    def test_default_service_when_no_compose_file_lists_one(self):
        self.assertEqual(self.runner().service, "laravel.test")
        self.compose("services:\n  db:\n    image: mysql\n")
        self.assertEqual(self.runner().service, "laravel.test")
        self.compose("services: {}\n")
        self.assertEqual(self.runner(defaults=dict(services=("php",), root="/var/www/html")).service, "php")

    def test_first_default_present_in_compose_wins(self):
        self.compose(COMPOSE)
        self.assertEqual(self.runner().service, "laravel.test")
        self.assertEqual(self.runner(defaults=dict(services=("missing", "php"), root="/app")).service, "php")

    def test_nested_keys_are_not_services(self):
        self.compose("services:\n  web:\n    environment:\n      php: ignored\n")
        self.assertEqual(self.runner(defaults=dict(services=("php", "web"), root="/app")).service, "web")

    def test_config_overrides_compose_and_env_overrides_config(self):
        self.compose(COMPOSE)
        self.assertEqual(self.runner({"service": "web"}).service, "web")
        self.assertEqual(self.runner({"service": "web"}, LINT_SERVICE="php").service, "php")

    def test_container_root_order(self):
        self.assertEqual(self.runner().root, "/app")
        self.assertEqual(self.runner({"container_root": "/srv"}).root, "/srv")
        self.assertEqual(self.runner({"container_root": "/srv"}, LINT_CONTAINER_ROOT="/opt").root, "/opt")

    def test_invalid_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "service"):
            self.runner({"service": "bad name"})
        with self.assertRaisesRegex(ValueError, "service"):
            self.runner(LINT_SERVICE="a;b")
        with self.assertRaisesRegex(ValueError, "absolute"):
            self.runner({"container_root": "relative/path"})

    def test_local_runner_uses_project_root(self):
        with patch.dict(os.environ, {"LINT_RUNNER": "local", "LINT_CONTAINER_ROOT": "/ignored"}, clear=True):
            runner = Runner(self.project, {}, self.defaults)
        self.assertEqual(runner.root, str(self.project))


class SharedCoreTest(unittest.TestCase):
    def test_shared_modules_have_no_profile_specific_strings(self):
        files = sorted(SHARED.glob("*/*.py"))
        self.assertTrue(files)
        for path in files:
            text = path.read_text(encoding="utf-8").lower()
            for word in ("drupal", "dpm", "kint", "laravel", "symfony"):
                with self.subTest(file=path.name, word=word):
                    self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
