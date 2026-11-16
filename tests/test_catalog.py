import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("validate_catalog", ROOT / "scripts/validate-catalog.py")
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


class CatalogTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="keledones-test.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

        for path, manifest in catalog.CATALOGS.values():
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, self.root / path)
            target = self.root / "plugins/ready-check" / manifest
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"name": "ready"}))

        self.original = catalog.ROOT
        catalog.ROOT = self.root
        self.addCleanup(setattr, catalog, "ROOT", self.original)

    def change(self, client, update):
        path = self.root / catalog.CATALOGS[client][0]
        data = json.loads(path.read_text())
        update(data)
        path.write_text(json.dumps(data))

    def assert_fails(self, text):
        with self.assertRaises(ValueError) as error:
            catalog.validate()
        self.assertIn(text, str(error.exception))

    def test_repository_catalogs_are_valid(self):
        catalog.ROOT = self.original
        self.assertEqual(catalog.validate(), {"ready": "ready-check"})

    def test_source_outside_plugins_is_rejected(self):
        self.change("cursor", lambda data: data["plugins"][0].update(source="../elsewhere"))
        self.assert_fails("relative source inside the repository")

    def test_codex_needs_a_local_source(self):
        self.change("codex", lambda data: data["plugins"][0].update(source={"source": "git", "url": "https://example.invalid/x.git"}))
        self.assert_fails("must use a local source")

    def test_name_must_match_the_plugin_manifest(self):
        (self.root / "plugins/ready-check/.claude-plugin/plugin.json").write_text(json.dumps({"name": "other"}))
        self.assert_fails("differs from the name")

    def test_catalogs_must_list_the_same_plugins(self):
        (self.root / "plugins/second/.cursor-plugin").mkdir(parents=True)
        (self.root / "plugins/second/.cursor-plugin/plugin.json").write_text(json.dumps({"name": "second"}))
        self.change("cursor", lambda data: data["plugins"].append({"name": "second", "source": "plugins/second"}))
        self.assert_fails("cursor lists")

    def test_unlisted_plugin_folder_is_reported(self):
        (self.root / "plugins/forgotten").mkdir()
        self.assert_fails("missing from the catalogs: forgotten")


if __name__ == "__main__":
    unittest.main()
