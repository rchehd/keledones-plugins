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

            for entry in json.loads((ROOT / path).read_text())["plugins"]:
                source = entry["source"]["path"] if isinstance(entry["source"], dict) else entry["source"]
                self.manifest(source, manifest, entry["name"])

        self.original = catalog.ROOT
        catalog.ROOT = self.root
        self.addCleanup(setattr, catalog, "ROOT", self.original)

    def manifest(self, folder, manifest, name):
        target = self.root / folder / manifest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"name": name}))

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
        self.assertEqual(catalog.validate(), {"ready-check": ("ready", ["claude", "codex", "cursor"]),
                                              "keledones-themes": ("keledones-themes", ["claude"]),
                                              "gnothi": ("gnothi", ["claude", "codex", "cursor"])})

    def test_source_outside_plugins_is_rejected(self):
        self.change("cursor", lambda data: data["plugins"][0].update(source="../elsewhere"))
        self.assert_fails("relative source inside the repository")

    def test_codex_needs_a_local_source(self):
        self.change("codex", lambda data: data["plugins"][0].update(source={"source": "git", "url": "https://example.invalid/x.git"}))
        self.assert_fails("must use a local source")

    def test_name_must_match_the_plugin_manifest(self):
        (self.root / "plugins/ready-check/.claude-plugin/plugin.json").write_text(json.dumps({"name": "other"}))
        self.assert_fails("differs from the name")

    def test_a_plugin_for_one_client_is_listed_only_there(self):
        self.assertEqual(catalog.validate()["keledones-themes"], ("keledones-themes", ["claude"]))

    def test_a_manifest_without_its_catalog_entry_is_reported(self):
        self.manifest("plugins/keledones-themes", ".cursor-plugin/plugin.json", "keledones-themes")
        self.assert_fails("has a cursor manifest but is missing from the cursor catalog")

    def test_one_folder_cannot_have_two_names(self):
        self.manifest("plugins/ready-check", ".cursor-plugin/plugin.json", "other")
        self.change("cursor", lambda data: data["plugins"][0].update(name="other"))
        self.assert_fails("listed under two names")

    def test_folder_without_a_manifest_is_reported(self):
        (self.root / "plugins/forgotten").mkdir()
        self.assert_fails("plugins/forgotten has no plugin manifest")


if __name__ == "__main__":
    unittest.main()
